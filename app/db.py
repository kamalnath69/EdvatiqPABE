from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

# load env early so other modules have access to variables
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/sports_app")
client = AsyncIOMotorClient(MONGODB_URI)
db = client.get_default_database()
