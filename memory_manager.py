from mem0 import MemoryClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Mem0 client
MEM0_API_KEY = os.getenv("MEM0_API_KEY")
mem0_client = MemoryClient(api_key=MEM0_API_KEY)

def add_memory(phone_number: str, role: str, content: str):
    """
    Add a message to a user's memory, with custom categories and custom prompt to 
    guide Mem0 in extracting best call times or call preferences.
    """
    try:
        # Prepare the payload for Mem0
        messages = [{"role": role, "content": content}]
        
        custom_categories = [
            {"personal_details": "Information related to the user's identity or personal attributes, such as their name, age, place of residence, or occupation."},
            {"family": "Details about the user's family members, relationships, family history, or events involving relatives."},
            {"professional_details": "Information pertaining to the user's current or past professions, careers, work experiences, and achievements in their professional life."},
            {"sports": "References to any sports the user follows, participates in, or discusses, including team names, matches, personal performance, or sports-related interests."},
            {"travel": "Mentions of travel destinations, trips, vacations, favorite places visited, or future travel plans."},
            {"food": "References to meals, dietary preferences, recipes, cooking habits, culinary experiences, and favorite dishes."},
            {"music": "Mentions of musical preferences, favorite songs, artists, genres, concerts, or past musical experiences."},
            {"health": "Information about the user's health conditions, medication, exercise habits, doctor visits, and general well-being."},
            {"technology": "Any details related to technology usage, devices the user owns or uses, technical support needs, or discussions about modern tech."},
            {"hobbies": "Information about the user's leisure activities, crafts, collections, games, gardening, or other pastimes they enjoy."},
            {"fashion": "Mentions of clothing preferences, style, shopping experiences, or any fashion-related interests."},
            {"entertainment": "Discussions about movies, TV shows, theater, books, radio programs, or other forms of entertainment."},
            {"milestones": "Significant life events, anniversaries, birthdays, graduations, retirements, or other key personal milestones."},
            {"user_preferences": "General personal likes, dislikes, comfort levels, routines, and preferences that don't fit into more specific categories."},
            {"misc": "Any content or references that don't clearly match other defined categories."},

            # Additional helpful categories
            {"call_schedule": "Extract any mention of the best time for the user to receive calls, including preferred times or schedules."},
            {"daily_routine": "Mentions of the user's regular daily activities, such as wake-up times, meal times, walk schedules, or evening rituals."},
            {"emotional_state": "References to the user's feelings, mood, emotional well-being, loneliness, happiness, or frustration."},
            {"memories": "Conversations involving reminiscing about the past, nostalgic stories, childhood memories, and life reflections."},
            {"care_instructions": "Important instructions or reminders related to medication, therapy sessions, medical appointments, or personal care routines."}
        ]

        response = mem0_client.add(
            messages=messages,
            user_id=phone_number,
            custom_categories=custom_categories,
        )
        
    except Exception as e:
        print(f"Error adding memory for {phone_number}: {e}")


def get_memory_context(phone_number, limit=10):
    """
    Retrieve the recent chat context for a user.
    """
    try:
        memories = mem0_client.get_all(user_id=phone_number)
        return [memory["memory"] for memory in memories[-limit:]]
    except Exception as e:
        print(f"Error retrieving context for {phone_number}: {e}")
        return []


def clear_memory(phone_number):
    """
    Clear the chat history for a user by deleting each memory individually.
    """
    try:
        memories = mem0_client.get_all(user_id=phone_number)
        for memory in memories:
            memory_id = memory["id"]
            mem0_client.delete(memory_id=memory_id)  # Delete each memory
        print(f"Memory cleared for {phone_number}")
    except Exception as e:
        print(f"Error clearing memory for {phone_number}: {e}")
