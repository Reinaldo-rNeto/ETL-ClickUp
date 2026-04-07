import os
import sys
import json
from clickup_client import ClickUpClient
from data_writer import DataWriter
from attachment_downloader import AttachmentDownloader
from dotenv import load_dotenv

load_dotenv() # Force load .env for testing
client = ClickUpClient()
writer = DataWriter()
downloader = AttachmentDownloader()

print("TEST 1: ATTACHMENT DOWNLOADER RAW OVERRIDE")
# Fetch the subtask with the image
t_img = client.get_task("86afqk2ud")
print("Task fetched:", t_img.get("name") if t_img else "None")
comms = client.get_task_comments("86afqk2ud")
print("Comments count:", len(comms) if comms else 0)

# Simulate extraction
print("Extracting attachments from comments...")
atts = downloader.extract_attachments_from_comments(comms)
print("Attachments found in comments:", atts)

print("\nTEST 2: PARENT TASK RESCUE AND PDF GENERATION")
# Fetch parent task directly to simulate Rescue
t_parent = client.get_task("86afkmify")
print("Parent Task Fetched:", t_parent.get("name") if t_parent else "None")
if t_parent:
    print("Testing PDF Generation manually for Parent...")
    try:
        path = writer.create_hierarchy("DEBUG_SPACE", "DEBUG_FOLDER", "DEBUG_LIST", t_parent.get("id"), t_parent.get("name"), t_parent.get("parent"))
        print("Hierarchy created at:", path)
        txt = writer.save_human_readable_log(path, t_parent, [])
        print("TXT Created:", txt)
        pdf = writer.save_human_readable_pdf(path, t_parent, [])
        print("PDF Created:", pdf)
    except Exception as e:
        import traceback
        traceback.print_exc()

print("FINISHED DEBUG SCRIPT")
