from mem0 import Memory

# Global dictionary to store user memories by phone number
user_memories = {}

def get_user_memory(phone_number):
    """
    Get or create a memory instance for a specific user based on their phone number.
    """
    if phone_number not in user_memories:
        user_memories[phone_number] = Memory()
    return user_memories[phone_number]

def add_message(phone_number, role, content):
    """
    Add a message to the user's memory.
    :param phone_number: User's phone number
    :param role: "user" or "assistant"
    :param content: Message content
    """
    memory = get_user_memory(phone_number)
    memory.add({"role": role, "content": content})

def get_context(phone_number, limit=10):
    """
    Retrieve the most recent messages from the user's memory.
    :param phone_number: User's phone number
    :param limit: Number of messages to retrieve
    :return: List of recent messages
    """
    memory = get_user_memory(phone_number)
    return memory.get_recent(limit=limit)

def clear_memory(phone_number):
    """
    Clear all chat history for a user.
    :param phone_number: User's phone number
    """
    if phone_number in user_memories:
        user_memories[phone_number] = Memory()