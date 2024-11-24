from mem0 import MemoryClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Mem0 client
MEM0_API_KEY = os.getenv("MEM0_API_KEY")
mem0_client = MemoryClient(api_key=MEM0_API_KEY)


def add_memory(phone_number, role, content):
    """
    Add a message to a user's memory.
    :param phone_number: The user's phone number (acts as user ID).
    :param role: Role of the message sender ("user" or "assistant").
    :param content: Message content to be stored.
    """
    try:
        mem0_client.add(
            messages=[{"role": role, "content": content}],
            user_id=phone_number,
        )
        print(f"Memory added for {phone_number}: {content}")
    except Exception as e:
        print(f"Error adding memory for {phone_number}: {e}")


def get_memory_context(phone_number, limit=10):
    """
    Retrieve the recent chat context for a user.
    :param phone_number: The user's phone number (acts as user ID).
    :param limit: Number of recent messages to retrieve.
    :return: List of recent messages.
    """
    try:
        memories = mem0_client.get_all(user_id=phone_number)
        return [memory["data"]["memory"] for memory in memories[-limit:]]
    except Exception as e:
        print(f"Error retrieving context for {phone_number}: {e}")
        return []


def clear_memory(phone_number):
    """
    Clear the chat history for a user.
    :param phone_number: The user's phone number (acts as user ID).
    """
    try:
        mem0_client.delete(user_id=phone_number)
        print(f"Memory cleared for {phone_number}")
    except Exception as e:
        print(f"Error clearing memory for {phone_number}: {e}")
