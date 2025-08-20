import csv
import json
import logging
from io import StringIO
import os

import uvicorn
from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import StreamingResponse
from firebase_admin import firestore
import scannerSecret
from model.scanResult import ScanResult
from scannerUtils.database import get_attendance_count, reset_firestore_attendance, update_ticket_status, update_firestore_ticket_status, get_all_mongo_entries, get_all_firestore_entries
from scannerUtils.resultJson import load_tickets, save_tickets
from scannerUtils.serialRegex import extract_serial_number

scanner = FastAPI()
scanner.add_middleware(SessionMiddleware, secret_key="your-secret-key")

logging.basicConfig(filename='scanner.log', level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
scanner.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@scanner.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(name='index.html', context={'request': request})


@scanner.post('/login')
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    if email.strip() == scannerSecret.username and password.strip() == scannerSecret.password:
        request.session["user"] = email.strip()
        return RedirectResponse(url="/dashboard", status_code=303)
    else:
        response = RedirectResponse(url="/", status_code=303)
        return response


@scanner.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    session_user = request.session.get("user")
    if session_user:
        # Get attendance count
        present_count = await get_attendance_count()
        
        # Get total entries count
        entries = await get_all_firestore_entries()
        total_count = len(entries)
        
        return templates.TemplateResponse(
            name="dashboard.html", 
            context={
                "request": request, 
                "user": session_user,
                "present_count": present_count,
                "total_count": total_count
            }
        )
    else:
        response = RedirectResponse(url="/", status_code=303)
        return response

@scanner.get("/registered-user")
async def registered_user(request: Request):
    entries = await get_all_firestore_entries()
    present_count = await get_attendance_count()
    return templates.TemplateResponse(
        'registered_users.html', 
        context={
            "request": request, 
            "entries": entries,
            "present_count": present_count,
            "total_count": len(entries)
        }
    )


@scanner.post("/scan-result")
async def scan_result(scan_data: ScanResult):
    qr_code_data = scan_data.qr_code
    tickets = load_tickets()
    ticket = {
        "qr_code": qr_code_data,
        "status": "scanned"
    }
    tickets.append(ticket)
    save_tickets(tickets)
    serial_number = extract_serial_number(qr_code_data)
    result = await update_ticket_status(serial_number)
    result = await update_firestore_ticket_status(serial_number)
    if result:
        return {"message": "Scan and update success", "ticket": ticket}

    if serial_number is None:
        return {"message": "Serial number not found in the data"}

    return {"message": "Scan success", "ticket": ticket}


@scanner.get("/registered-user")
async def registered_user(request: Request):
    # entries = await get_all_mongo_entries()
    entries = await get_all_firestore_entries()
    return templates.TemplateResponse('registered_users.html', context={"request": request, "entries": entries})


@scanner.get("/download-csv")
async def download_csv():
    csv_output = StringIO()
    # entries = await get_all_mongo_entries()
    entries = await get_all_firestore_entries()
    headers = list(entries[0].keys())
    writer = csv.DictWriter(csv_output, fieldnames=headers)
    writer.writeheader()

    for entry in entries:
        entry['sno'] = str(entry['sno'])
        writer.writerow(entry)

    csv_output.seek(0)

    return StreamingResponse(csv_output, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=entries.csv"})



#reset attendance

@scanner.post("/reset-attendance")
async def reset_attendance(request: Request):
    session_user = request.session.get("user")
    if not session_user:
        return RedirectResponse(url="/", status_code=303)
    
    try:
        # Reset attendance in Firestore
        await reset_firestore_attendance()
        
        # Also reset the local tickets if needed
        tickets = load_tickets()
        for ticket in tickets:
            ticket["status"] = "not_scanned"
        save_tickets(tickets)
        
        return RedirectResponse(url="/dashboard", status_code=303)
    except Exception as e:
        logging.error(f"Error resetting attendance: {e}")
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": session_user, "error": "Failed to reset attendance"}
        )
    
@scanner.get("/debug-firebase")
async def debug_firebase():
    firebase_creds = os.getenv("FIREBASE_CREDS")
    if firebase_creds:
        try:
            # Try to parse the JSON
            creds_dict = json.loads(firebase_creds)
            return {
                "status": "success",
                "keys": list(creds_dict.keys()),
                "type": type(firebase_creds).__name__,
                "length": len(firebase_creds)
            }
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "message": f"Invalid JSON: {str(e)}",
                "first_100_chars": firebase_creds[:100] if firebase_creds else None
            }
    else:
        return {
            "status": "error",
            "message": "FIREBASE_CREDS environment variable not set"
        }

@scanner.get("/test-firebase")
async def test_firebase():
    try:
        db = firestore.client()
        collection = db.collection("friends")
        docs = collection.limit(1).stream()
        for doc in docs:
            return {"status": "success", "doc_id": doc.id}
        return {"status": "success", "message": "Connected but no documents found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# if __name__ == "__main__":
#     uvicorn.run(app="webScanner:scanner", host='127.0.0.1', port=8000)
