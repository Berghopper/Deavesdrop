import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from discord import ApplicationContext
import time

# app-only file access
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveUploader:
    def __init__(self, token_file):
        self.token_file = token_file
        self.service = None
        self.creds = None
        # self.service, self.creds = GoogleDriveUploader.build_service(ctx, token_file)

    def init_auth(self, ctx) -> bool:
        self.service, self.creds = GoogleDriveUploader.build_service(
            ctx, self.token_file
        )
        if self.service and self.creds:
            return True
        return False

    def build_service(
        ctxs: list[ApplicationContext], token_file
    ) -> tuple[Resource, Credentials]:
        creds = None
        if token_file and os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                for ctx in ctxs:
                    ctx.send(
                        "Please contact the bot owner to authenticate with Google Drive API, token has expired/is invalid or missing."
                    )
                return None, None
            # Save the credentials for the next run if token_file is provided
            if token_file:
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
        return build("drive", "v3", credentials=creds), creds

    def check_if_file_exists(self, file_name, g_folder_id):
        # Check if file exists in the folder
        query = f"name='{file_name}' and '{g_folder_id}' in parents"
        response = self.service.files().list(q=query).execute()
        files = response.get("files", [])
        return len(files) > 0

    def upload_resumable(self, file_path, g_folder_id):
        if not self.service or not self.creds:
            raise ValueError("Google Drive API not authenticated.")
        file_name = os.path.basename(file_path)

        metadata = {
            "name": file_name,
            "parents": [g_folder_id],
        }

        try:
            media_body = MediaFileUpload(file_path, resumable=True)
            file = (
                self.service.files()
                .create(body=metadata, media_body=media_body)
                .execute()
            )
            return file.get("id")
        except HttpError as error:
            print(f"GDRIVE An error occurred: {error}")
            return None
