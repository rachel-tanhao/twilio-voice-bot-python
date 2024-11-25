# This file automatically calls the functions at set periods in the day to check in on the user

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from voice_handler import make_call
from datetime import datetime, timedelta

# Replace with the phone number you want to call
PHONE_NUMBER = '+1234567890'  # Replace with the actual phone number

async def scheduled_call():
    await make_call(PHONE_NUMBER)

if __name__ == '__main__':
    scheduler = AsyncIOScheduler()
    # Schedule the calls at specific times
    scheduler.add_job(scheduled_call, 'cron', hour=9, minute=0)   # At 9:00 AM
    scheduler.add_job(scheduled_call, 'cron', hour=18, minute=0)  # At 6:00 PM
    scheduler.start()

    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass

# Uncomment if you want to test - will call in 30 seconds

# scheduler.add_job(
#     scheduled_call, 
#     'date', 
#     run_date=datetime.now() + timedelta(seconds=30)
# )