import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from firebase_admin import credentials, firestore, initialize_app
from urllib.parse import quote_plus
import asyncio
import json
import tempfile
import os
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("MONGO_USERNAME")
password = os.getenv("MONGO_PASSWORD")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)
# username = "onam2025"
# password = "Onam@2025"  # example with special characters



# Initialize Firebase using environment variables
def initialize_firebase():
    firebase_creds = os.getenv("FIREBASE_CREDS")
    if firebase_creds:
        try:
            # Try to parse the JSON directly
            creds_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(creds_dict)
            initialize_app(cred)
            return
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Firebase credentials JSON: {e}")
            # If JSON parsing fails, write to a temporary file
            try:
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp:
                    temp.write(firebase_creds)
                    temp_path = temp.name
                cred = credentials.Certificate(temp_path)
                initialize_app(cred)
                # Clean up the temporary file
                os.unlink(temp_path)
                return
            except Exception as e:
                logger.error(f"Error using temporary file for Firebase credentials: {e}")
                # Fall back to local file if available
                pass
    
    # Fallback to local file (for development)
    try:
        cred = credentials.Certificate("scannerUtils/refl-onam-firebase-adminsdk-5f38f-981e1b4cd9.json")
        initialize_app(cred)
        return
    except FileNotFoundError:
        logger.error("Firebase credentials file not found and environment variable not set")
        raise ValueError("Firebase credentials not found. Please set FIREBASE_CREDS environment variable.")

# Initialize Firebase
initialize_firebase()


async def update_ticket_status(serial_number: int):
    try:
        encoded_username = quote_plus(username)
        encoded_password = quote_plus(password)
        client = AsyncIOMotorClient(f"mongodb+srv://{encoded_username}:{encoded_password}@onamcluster.vwvjoqi.mongodb.net/")
        db = client["onamdb"]
        collection = db["ticketstable"]
        logger.info("MongoDB connection created successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB: {e}")
        return
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        result = await collection.update_one(
            {"sno": serial_number},
            {"$set": {
                "attendance": True,
                "attendance_time": current_time,
                "ticket_shared_status": True
            }}
        )
        if result.modified_count > 0:
            logger.info(f"Successfully updated ticket status for serial number {serial_number}.")
        else:
            logger.warning(f"No matching document found for serial number {serial_number}.")
    except Exception as e:
        logger.error(f"Failed to update ticket status: {e}")

cred = credentials.Certificate("scannerUtils/refl-onam-firebase-adminsdk-5f38f-981e1b4cd9.json")
initialize_app(cred)
async def update_firestore_ticket_status(serial_number: int):
    db = firestore.client()
    collection = db.collection("friends")
    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Looking for document with sno: {serial_number}")
        
        # First, let's check if we can find any documents with this sno
        query = collection.where('sno', '==', serial_number).limit(1)
        docs = list(query.stream())
        
        if not docs:
            logger.warning(f"No document found with sno: {serial_number}")
            # Let's log some sample documents to see what we have
            sample_docs = list(collection.limit(3).stream())
            logger.info(f"Sample documents in collection:")
            for doc in sample_docs:
                logger.info(f"Document ID: {doc.id}, Data: {doc.to_dict()}")
            return False
        
        # If we found documents, update the first one
        doc = docs[0]
        doc_data = doc.to_dict()
        logger.info(f"Found document: {doc.id}, Current data: {doc_data}")
        
        # Perform the update
        update_data = {
            "attendance": True,
            "attendance_time": current_time,
            "ticket_shared_status": True
        }
        doc.reference.update(update_data)
        logger.info(f"Successfully updated document {doc.id} with: {update_data}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update Firestore ticket status: {e}")
        return False

async def get_all_mongo_entries():
    try:
        client = AsyncIOMotorClient("mongodb://localhost:27017/")
        db = client["xmas_friend"]
        collection = db["friends"]
        entries = await collection.find().to_list(length=100)
        logger.info(f"Retrieved {len(entries)} entries from MongoDB.")
        return entries
    except Exception as e:
        logger.error(f"Failed to retrieve entries from MongoDB: {e}")
        return []

async def get_all_firestore_entries():
    try:
        db = firestore.client()
        collection = db.collection("friends")
        docs = collection.stream()
        entries = []
        seen_snos = set()  # Track seen serial numbers to identify duplicates
        
        for doc in docs:
            entry = doc.to_dict()
            # Ensure we have all fields
            if 'attendance' not in entry:
                entry['attendance'] = False
            if 'attendance_time' not in entry:
                entry['attendance_time'] = None
                
            # Check for duplicates using 'sno' field
            if 'sno' in entry:
                if entry['sno'] not in seen_snos:
                    entries.append(entry)
                    seen_snos.add(entry['sno'])
                else:
                    logger.warning(f"Duplicate entry found with sno: {entry['sno']}")
            else:
                # If no sno field, still add the entry but log a warning
                entries.append(entry)
                logger.warning("Entry found without sno field")
                
        logger.info(f"Retrieved {len(entries)} unique entries from Firestore.")
        return entries
    except Exception as e:
        logger.error(f"Failed to retrieve entries from Firestore: {e}")
        return []

async def reset_firestore_attendance():
    try:
        # Use the same client as other functions
        db = firestore.client()
        tickets_ref = db.collection('friends')
        
        # Get all documents in the collection
        docs = tickets_ref.stream()
        count = 0
        
        # Update each document to reset attendance
        for doc in docs:
            doc.reference.update({
                'attendance': False,
                'attendance_time': None  # Also reset the time
            })
            count += 1
        
        logger.info(f"Reset attendance for {count} documents.")
        return True
    except Exception as e:
        logger.error(f"Failed to reset Firestore attendance: {e}")
        return False
    
async def get_attendance_count():
    try:
        db = firestore.client()
        collection = db.collection("friends")
        
        # Query for documents where attendance is True
        query = collection.where('attendance', '==', True)
        docs = query.stream()
        
        # Count the documents
        count = sum(1 for _ in docs)
        logger.info(f"Retrieved attendance count: {count} attendees marked as present.")
        return count
    except Exception as e:
        logger.error(f"Failed to get attendance count: {e}")
        return 0
    
async def remove_duplicate_firestore_entries():
    try:
        db = firestore.client()
        collection = db.collection("friends")
        docs = collection.stream()
        
        # Group entries by sno
        entries_by_sno = {}
        duplicates_count = 0
        
        for doc in docs:
            entry = doc.to_dict()
            if 'sno' in entry:
                sno = entry['sno']
                if sno not in entries_by_sno:
                    entries_by_sno[sno] = []
                entries_by_sno[sno].append(doc)
        
        # Process each group of duplicates
        for sno, doc_list in entries_by_sno.items():
            if len(doc_list) > 1:
                duplicates_count += len(doc_list) - 1
                # Keep the most recently updated document
                # Sort by attendance_time if available, otherwise by document ID
                doc_list.sort(key=lambda doc: (
                    doc.to_dict().get('attendance_time', '') or '',
                    doc.id
                ), reverse=True)
                
                # Delete all but the first (most recent) document
                for doc in doc_list[1:]:
                    doc.reference.delete()
                    logger.info(f"Deleted duplicate document with sno: {sno}, id: {doc.id}")
        
        logger.info(f"Removed {duplicates_count} duplicate entries from Firestore.")
        return True
    except Exception as e:
        logger.error(f"Failed to remove duplicates from Firestore: {e}")
        return False