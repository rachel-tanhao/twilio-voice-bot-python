from mem0 import Memory

# 全局用户内存
user_memories = {}

def get_user_memory(phone_number):
    """
    获取或创建用户内存。
    每个电话号码（用户）都有独立的 Memory 实例。
    """
    if phone_number not in user_memories:
        user_memories[phone_number] = Memory()
    return user_memories[phone_number]

def add_message(phone_number, role, content):
    """
    将新的消息存储到用户的 Memory 实例中。
    :param phone_number: 用户的电话号码，用于区分不同的用户
    :param role: 消息发送方 ("user" 或 "assistant")
    :param content: 消息内容
    """
    memory = get_user_memory(phone_number)
    memory.add({"role": role, "content": content})

def get_context(phone_number, limit=10):
    """
    获取用户最近的聊天上下文。
    :param phone_number: 用户的电话号码
    :param limit: 获取的消息条数
    :return: 最近聊天记录的列表
    """
    memory = get_user_memory(phone_number)
    return memory.get_recent(limit=limit)

def clear_memory(phone_number):
    """
    清空指定用户的聊天记录。
    :param phone_number: 用户的电话号码
    """
    if phone_number in user_memories:
        user_memories[phone_number] = Memory()


def get_all_memories():
    """
    获取所有用户的记忆。
    :return: 一个包含所有用户记忆的字典
    """
    all_memories = {}
    for phone_number, memory in user_memories.items():
        all_memories[phone_number] = memory.get_all()  # 使用 mem0 的 get_all 方法
    return all_memories
