# This file automatically calls the functions at set periods in the day to check in on the user

import asyncio
import re
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from voice_handler import make_call
from memory_manager import get_call_schedule

# Replace with the phone numbers you want to call
PHONE_NUMBER1 = '+14452607227'  # Hao
PHONE_NUMBER2 = '+12156005826'  # Steven
TEST = '+18573523420'

def parse_time_from_text(text):
    """
    Parse a time from text using regular expressions.
    Supports formats like '3 PM', '15:30', 'call me at 9am', etc.
    """
    # Define patterns to match various time formats
    time_patterns = [
        r'\b(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\b',   # Matches HH:MM, optionally with AM/PM
        r'\b(\d{1,2})\s*([AaPp][Mm])\b',            # Matches HH AM/PM
        r'(?i)\bcall.*at\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm]?)\b', # Matches 'call me at HH:MM AM/PM'
        r'(?i)\bcall.*at\s*(\d{1,2})\s*([AaPp][Mm])\b',          # Matches 'call me at HH AM/PM'
    ]

    for pattern in time_patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            hour = int(groups[0])
            minute = int(groups[1]) if len(groups) > 1 and groups[1] and groups[1].isdigit() else 0
            am_pm = groups[-1].lower() if groups[-1] else ''

            # Convert to 24-hour format if necessary
            if am_pm == 'pm' and hour < 12:
                hour += 12
            if am_pm == 'am' and hour == 12:
                hour = 0

            return hour, minute
    return None


def get_preferred_call_time(phone_number):
    """
    Retrieves the preferred call time from the user's memory context.
    """
    memory_context = get_call_schedule(phone_number)
    for memory in reversed(memory_context):  # Start from the most recent messages
        # Handle both dictionary and string formats
        if isinstance(memory, dict):
            content = memory.get('content', '')
            role = memory.get('role', '')
            if role == 'user' and content:
                time_result = parse_time_from_text(content)
                if time_result:
                    return time_result
        elif isinstance(memory, str):
            # If memory is a string, parse it directly
            time_result = parse_time_from_text(memory)
            if time_result:
                return time_result
    return None  # No preferred time found

async def scheduled_call(phone_number):
    print(f"Making call to {phone_number} at {datetime.now().strftime('%H:%M:%S')}")
    
    # Check for existing future jobs for this phone number
    existing_jobs = [
        job for job in scheduler.get_jobs() 
        if job.args == [phone_number] and job.next_run_time > datetime.now()
    ]
    
    # Get the most recent job's scheduled time
    if existing_jobs:
        most_recent_job = max(existing_jobs, key=lambda x: x.next_run_time)
        time_since_last_scheduled = (datetime.now() - most_recent_job.next_run_time).total_seconds()
        
        # If less than 5 minutes since last call, skip scheduling
        if abs(time_since_last_scheduled) < 300:  # 300 seconds = 5 minutes
            print(f"Skipping new schedule - too close to previous call for {phone_number}")
            return

    await make_call(phone_number)
    
    # After the call, check if the user specified a new preferred time
    preferred_time = get_preferred_call_time(phone_number)
    if preferred_time:
        hour, minute = preferred_time
        
        # Calculate the proposed call time
        now = datetime.now()
        proposed_time = now.replace(hour=hour, minute=minute)
        
        # If the proposed time is in the past, schedule for tomorrow
        if proposed_time < now:
            proposed_time = proposed_time + timedelta(days=1)
            
        # Ensure minimum gap of 5 minutes from now
        if (proposed_time - now).total_seconds() < 300:
            print(f"Requested time too soon. Scheduling for tomorrow instead.")
            proposed_time = proposed_time + timedelta(days=1)
        
        # Cancel existing jobs for this phone number
        for job in scheduler.get_jobs():
            if job.args == [phone_number]:
                scheduler.remove_job(job.id)
                
        # Schedule new job
        scheduler.add_job(
            scheduled_call,
            'date',
            run_date=proposed_time,
            args=[phone_number]
        )
        print(f"Scheduled call for {phone_number} at {proposed_time.strftime('%H:%M:%S')}")
    else:
        print(f"No preferred time found for {phone_number}")

if __name__ == '__main__':
    scheduler = AsyncIOScheduler()
    
    # Get preferred time for each phone number you want to call
    phone_numbers = [TEST, PHONE_NUMBER1, PHONE_NUMBER2]  # Add all phone numbers you want to schedule
    
    for phone_number in phone_numbers:
        preferred_time = get_preferred_call_time(phone_number)
        
        if preferred_time:
            hour, minute = preferred_time
            
            # Calculate the proposed call time
            now = datetime.now()
            proposed_time = now.replace(hour=hour, minute=minute)
            
            # If the proposed time is in the past, schedule for tomorrow
            if proposed_time < now:
                proposed_time = proposed_time + timedelta(days=1)
                
            # Ensure minimum gap of 5 minutes from now
            if (proposed_time - now).total_seconds() < 300:
                proposed_time = proposed_time + timedelta(days=1)
            
            # Schedule the call
            scheduler.add_job(
                scheduled_call,
                'date',
                run_date=proposed_time,
                args=[phone_number]
            )
            print(f"Scheduled call for {phone_number} at {proposed_time.strftime('%H:%M:%S')}")
        else:
            print(f"No preferred time found for {phone_number}")

    scheduler.start()

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass