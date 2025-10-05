
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("DATABASE_URL")
# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))

database = client['ShopyGenie']

#creating collections
users_collection = database['users']
products_collection = database['products']
purchases_collection = database['purchases']
sales_collection = database['sales']
customers_collection = database['customers']
debts_collection = database['debts']
expenditures_collection = database['expenditures']

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)