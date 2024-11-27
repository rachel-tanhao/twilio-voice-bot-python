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
    Add a message to a user's memory.
    :param phone_number: The user's phone number (acts as user ID).
    :param role: Role of the message sender ("user" or "assistant").
    :param content: Message content to be stored (must be a string).
    """
    try:
        # Prepare the payload for Mem0
        messages = [{"role": role, "content": content}]

        # Send to Mem0 API
        response = mem0_client.add(
            messages=messages,
            user_id=phone_number,
        )

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
        # Fetch all memories for the user
        memories = mem0_client.get_all(user_id=phone_number)
        # print(f"Fetched memories for {phone_number}: {memories}")  # Debug the response

        # Extract the 'memory' key from each fetched memory and limit the results
        return [memory["memory"] for memory in memories[-limit:]]
    except Exception as e:
        print(f"Error retrieving context for {phone_number}: {e}")
        return []



def clear_memory(phone_number):
    """
    Clear the chat history for a user by deleting each memory individually.
    :param phone_number: The user's phone number (acts as user ID).
    """
    try:
        # Fetch all memories for the user
        memories = mem0_client.get_all(user_id=phone_number)
        for memory in memories:
            memory_id = memory["id"]
            mem0_client.delete(memory_id=memory_id)  # Delete each memory
        print(f"Memory cleared for {phone_number}")
    except Exception as e:
        print(f"Error clearing memory for {phone_number}: {e}")


