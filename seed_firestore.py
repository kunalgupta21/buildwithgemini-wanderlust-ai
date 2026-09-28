#!/usr/bin/env python3
"""Seed script to populate Firestore with sample destination data for Wanderlust AI."""

from google.cloud import firestore

# Hardcoded Project ID string as required for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-02-96687573d7d6"

SAMPLE_DESTINATIONS = [
    {
        "id": "dest_tokyo",
        "name": "Tokyo, Japan",
        "category": "Cultural & City",
        "description": "Vibrant metropolis blending ultra-modern skyscrapers, anime culture, ancient temples, and world-class culinary scenes.",
        "estimated_daily_cost_usd": 180.0,
        "best_season": "Spring & Autumn",
        "rating": 4.9,
        "highlights": ["Shibuya Crossing", "Meiji Shrine", "Tsukiji Outer Market", "Akihabara"]
    },
    {
        "id": "dest_paris",
        "name": "Paris, France",
        "category": "Romance & Art",
        "description": "The City of Light, famous for world-renowned art museums, iconic architecture, romantic boulevards, and exquisite pastries.",
        "estimated_daily_cost_usd": 220.0,
        "best_season": "Spring & Summer",
        "rating": 4.8,
        "highlights": ["Eiffel Tower", "Louvre Museum", "Montmartre", "Seine River Cruise"]
    },
    {
        "id": "dest_kyoto",
        "name": "Kyoto, Japan",
        "category": "Historical & Nature",
        "description": "Japan's cultural heart filled with thousands of classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses.",
        "estimated_daily_cost_usd": 150.0,
        "best_season": "Spring & Autumn",
        "rating": 4.9,
        "highlights": ["Fushimi Inari Shrine", "Arashiyama Bamboo Grove", "Kinkaku-ji (Golden Pavilion)", "Gion District"]
    },
    {
        "id": "dest_banff",
        "name": "Banff, Canada",
        "category": "Adventure & Nature",
        "description": "Breathtaking national park in the Canadian Rockies with turquoise glacial lakes, majestic peaks, and abundant mountain wildlife.",
        "estimated_daily_cost_usd": 200.0,
        "best_season": "Summer & Winter",
        "rating": 4.9,
        "highlights": ["Lake Louise", "Moraine Lake", "Banff Upper Hot Springs", "Johnston Canyon"]
    },
    {
        "id": "dest_amalfi",
        "name": "Amalfi Coast, Italy",
        "category": "Coastal & Luxury",
        "description": "Dramatic Mediterranean coastline featuring cliffside pastel villages, lemon groves, crystal waters, and world-famous seafood.",
        "estimated_daily_cost_usd": 250.0,
        "best_season": "Late Spring & Early Autumn",
        "rating": 4.8,
        "highlights": ["Positano Village", "Ravello Gardens", "Path of the Gods Hike", "Capri Boat Tour"]
    }
]


def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}...")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("destinations")

    for dest in SAMPLE_DESTINATIONS:
        doc_ref = collection_ref.document(dest["id"])
        doc_ref.set(dest)
        print(f"  ✓ Seeded destination: {dest['name']} ({dest['id']})")

    print(f"🎉 Successfully seeded {len(SAMPLE_DESTINATIONS)} destinations into Firestore collection 'destinations'.")


if __name__ == "__main__":
    seed_database()
