import datetime
import json
from zoneinfo import ZoneInfo

from .a2ui.basic_catalog.provider import BasicCatalog
from .a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

from .a2ui_utils import a2ui_callback

# Hardcoded Project ID string as required for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-02-96687573d7d6"

# Hardcoded Public Cloud Storage Bucket Name
BUCKET_NAME = "wanderlust-ai-assets-966875"

# Memory Bank / Agent Engine ID from deployment
MEMORY_BANK_ID = "3283535345701879808"

# Initialize Firestore client
db = firestore.Client(project=PROJECT_ID)

# Initialize Vertex AI Memory Bank Service for future deployment / runtime
memory_service = VertexAiMemoryBankService(
    project=PROJECT_ID,
    location="us-east1",
    agent_engine_id=MEMORY_BANK_ID,
)

# Build A2UI System Instruction Prompt using A2uiSchemaManager version 0.8
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Wanderlust AI, an expert travel concierge assistant. "
        "You help users discover travel destinations, search catalog recommendations from Firestore, "
        "calculate detailed trip budgets, generate scenic travel photos, check weather and local time, and save new destinations. "
        "You remember the user's stated preferences and facts from previous conversations and use them to personalize your responses."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


def search_destinations(category: str = "", max_daily_budget_usd: float = 0.0) -> str:
    """Searches travel destinations in the Firestore database filtered by category or max daily budget.

    Args:
        category: Optional category filter (e.g. 'Cultural & City', 'Romance & Art', 'Adventure & Nature', 'Coastal & Luxury').
        max_daily_budget_usd: Optional maximum daily budget in USD.

    Returns:
        A JSON string listing matching destinations.
    """
    collection_ref = db.collection("destinations")
    docs = collection_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        if category and category.lower() not in data.get("category", "").lower():
            continue
        if max_daily_budget_usd > 0 and data.get("estimated_daily_cost_usd", 0) > max_daily_budget_usd:
            continue
        results.append(data)

    if not results:
        return "No destinations found matching your criteria."
    return json.dumps(results, indent=2)


def get_destination_details(destination_id: str) -> str:
    """Retrieves full details for a specific travel destination from Firestore by destination ID or name lookup.

    Args:
        destination_id: The document ID (e.g., 'dest_tokyo') or name of the destination.

    Returns:
        A JSON string containing destination details, or an error message if not found.
    """
    doc_ref = db.collection("destinations").document(destination_id)
    doc = doc_ref.get()

    if doc.exists:
        return json.dumps(doc.to_dict(), indent=2)

    # Fallback to search by name if not matched by exact ID
    docs = db.collection("destinations").stream()
    for d in docs:
        data = d.to_dict()
        if destination_id.lower() in data.get("name", "").lower() or destination_id.lower() in data.get("id", "").lower():
            return json.dumps(data, indent=2)

    return f"Destination '{destination_id}' not found."


def save_destination(
    destination_id: str,
    name: str,
    category: str,
    description: str,
    estimated_daily_cost_usd: float,
    best_season: str,
    highlights: str,
) -> str:
    """Saves or updates a travel destination in the Firestore database.

    Args:
        destination_id: Unique identifier for the destination (e.g., 'dest_sydney').
        name: Name of the destination city and country (e.g., 'Sydney, Australia').
        category: Travel category (e.g., 'Coastal & Beach', 'Cultural & City').
        description: A compelling summary of what makes this destination special.
        estimated_daily_cost_usd: Estimated average daily cost in USD.
        best_season: Best time of year to visit (e.g., 'Spring & Summer').
        highlights: Comma-separated list of top attractions or highlights.

    Returns:
        A confirmation message upon successfully writing to Firestore.
    """
    highlights_list = [h.strip() for h in highlights.split(",") if h.strip()]
    doc_data = {
        "id": destination_id,
        "name": name,
        "category": category,
        "description": description,
        "estimated_daily_cost_usd": float(estimated_daily_cost_usd),
        "best_season": best_season,
        "rating": 4.8,
        "highlights": highlights_list,
    }

    doc_ref = db.collection("destinations").document(destination_id)
    doc_ref.set(doc_data)
    return f"Successfully saved destination '{name}' ({destination_id}) to Firestore."


def generate_destination_image(
    destination_name: str,
    prompt_details: str = "",
    tool_context: ToolContext = None,
) -> str:
    """Generates a high-quality scenic photo for a travel destination, saves it to Playground artifacts, and uploads it to public Cloud Storage.

    Args:
        destination_name: Name of the destination (e.g., 'Tokyo, Japan', 'Paris', 'Amalfi Coast').
        prompt_details: Additional visual scene details (e.g., 'cherry blossoms with Mount Fuji at sunset').
        tool_context: Injected tool context used to save artifacts.

    Returns:
        The public HTTPS URL of the image uploaded to Cloud Storage.
    """
    prompt = f"A vibrant, high quality scenic travel photograph of {destination_name}. {prompt_details}".strip()
    genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")

    response = genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )

    image_bytes = None
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            break

    if not image_bytes:
        return "Error: Image generation failed to return image bytes."

    clean_name = destination_name.lower().replace(" ", "_").replace(",", "").replace("/", "_")
    timestamp = int(datetime.datetime.now().timestamp())
    filename = f"{clean_name}_{timestamp}.jpg"

    # (1) Save artifact for Playground Artifacts panel
    if tool_context:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # (2) Upload image bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type="image/jpeg")

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    return f"Successfully generated image for '{destination_name}'. Public URL: {public_url}"


def get_weather(query: str) -> str:
    """Simulates weather search for travel destinations.

    Args:
        query: Destination location string.

    Returns:
        Simulated weather information.
    """
    query_lower = query.lower()
    if "tokyo" in query_lower or "kyoto" in query_lower:
        return "It's 68°F (20°C) and pleasant with clear skies."
    elif "paris" in query_lower:
        return "It's 62°F (17°C) and partly cloudy."
    elif "banff" in query_lower:
        return "It's 52°F (11°C) and crisp with fresh mountain air."
    elif "amalfi" in query_lower:
        return "It's 75°F (24°C) and sunny with coastal breeze."
    return "It's 72°F (22°C) and sunny."


def get_current_time(query: str) -> str:
    """Gets the current local time for a travel destination city.

    Args:
        query: City or country query.

    Returns:
        Current local time.
    """
    query_lower = query.lower()
    if "tokyo" in query_lower or "japan" in query_lower or "kyoto" in query_lower:
        tz_identifier = "Asia/Tokyo"
    elif "paris" in query_lower or "france" in query_lower or "amalfi" in query_lower or "italy" in query_lower:
        tz_identifier = "Europe/Paris"
    elif "banff" in query_lower or "canada" in query_lower:
        tz_identifier = "America/Edmonton"
    else:
        tz_identifier = "UTC"

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"Current local time in {query}: {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def calculate_trip_budget(
    daily_cost_usd: float,
    duration_days: int,
    num_travelers: int = 1,
    include_flight_estimate: bool = True,
) -> str:
    """Calculates a detailed itemized budget breakdown for a travel trip.

    Args:
        daily_cost_usd: Estimated daily cost per person in USD (lodging, food, activities).
        duration_days: Length of trip in days.
        num_travelers: Number of travelers.
        include_flight_estimate: Whether to include an estimated flight allowance ($600 per person).

    Returns:
        A JSON string containing the itemized trip budget breakdown.
    """
    daily_total = float(daily_cost_usd) * int(duration_days) * int(num_travelers)
    flight_estimate = (600.0 * int(num_travelers)) if include_flight_estimate else 0.0
    contingency_cushion = (daily_total + flight_estimate) * 0.10
    grand_total = daily_total + flight_estimate + contingency_cushion

    breakdown = {
        "duration_days": int(duration_days),
        "num_travelers": int(num_travelers),
        "daily_cost_per_person_usd": float(daily_cost_usd),
        "lodging_food_activities_total_usd": round(daily_total, 2),
        "estimated_flight_total_usd": round(flight_estimate, 2),
        "contingency_cushion_10pct_usd": round(contingency_cushion, 2),
        "grand_total_usd": round(grand_total, 2),
        "cost_per_traveler_usd": round(grand_total / int(num_travelers), 2),
    }
    return json.dumps(breakdown, indent=2)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        save_destination,
        generate_destination_image,
        calculate_trip_budget,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)




