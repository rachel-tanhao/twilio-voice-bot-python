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
            {
                "call_schedule": "Extract any mention of the best time for the user to receive calls, including preferred times or schedules."
            }
        ]

        # 定义 custom_prompt
        # 在这里提供few-shot示例，帮助mem0了解如何提取通话时间信息
        custom_prompt = """
            Please extract facts related to the user's best call time or call preferences.
            If no call time is mentioned, return an empty facts array.

            examples:

            Input: "Call me at 9 AM tomorrow"
            Output: {"facts": ["Best call time: 9 AM tomorrow"]}

            Input: "Can you ring me in the afternoon?"
            Output: {"facts": ["Potential call time: today afternoon"]}

            Input: "I went to the park yesterday"
            Output: {"facts": []}

            Make sure to return the extracted facts in the json format as shown.
        """

        # includes参数，用来强化只存储和提取与通话时间相关的信息
        includes = "best call time, user call schedule, preferred calling hours, call time preferences"

        # 调用mem0的add方法时增加custom_categories, custom_prompt和includes
        response = mem0_client.add(
            messages=messages,
            user_id=phone_number,
            custom_categories=custom_categories,
            custom_prompt=custom_prompt,
            includes=includes
        )
        print(response)

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
