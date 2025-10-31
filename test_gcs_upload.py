"""
Diagnostic script to test GCS upload functionality.
Run this script to verify your GCS configuration is working correctly.
"""
import os
import sys
import django
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pedal_point.settings')
django.setup()

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings

def test_gcs_connection():
    """Test GCS connection and upload."""
    print("=" * 60)
    print("GCS Configuration Test")
    print("=" * 60)
    
    # Check settings
    print(f"\n1. USE_GCS: {getattr(settings, 'USE_GCS', 'Not set')}")
    print(f"2. GS_BUCKET_NAME: {getattr(settings, 'GS_BUCKET_NAME', 'Not set')}")
    print(f"3. GS_PROJECT_ID: {getattr(settings, 'GS_PROJECT_ID', 'Not set')}")
    print(f"4. GS_CREDENTIALS: {getattr(settings, 'GS_CREDENTIALS', 'Not set')}")
    print(f"5. GOOGLE_APPLICATION_CREDENTIALS env: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'Not set')}")
    print(f"6. DEFAULT_FILE_STORAGE: {getattr(settings, 'DEFAULT_FILE_STORAGE', 'Not set')}")
    
    if not getattr(settings, 'USE_GCS', False):
        print("\n❌ ERROR: USE_GCS is not True. GCS is not enabled.")
        return False
    
    if not getattr(settings, 'GS_BUCKET_NAME', None):
        print("\n❌ ERROR: GS_BUCKET_NAME is not set.")
        return False
    
    if not getattr(settings, 'GS_CREDENTIALS', None):
        print("\n⚠️  WARNING: GS_CREDENTIALS is not set. Using default credentials if available.")
    
    # Test storage backend initialization
    print("\n" + "=" * 60)
    print("Testing Storage Backend Initialization")
    print("=" * 60)
    
    try:
        storage = default_storage
        print(f"Storage backend: {type(storage).__name__}")
        
        # Try to access bucket (this will fail if credentials are wrong)
        # django-storages lazy-loads the bucket, so we need to trigger it
        try:
            # Access bucket property to trigger initialization
            if hasattr(storage, 'bucket'):
                bucket = storage.bucket
                if bucket:
                    print(f"✅ Bucket initialized: {bucket.name}")
                    # Try to list bucket to verify access
                    try:
                        blobs = list(bucket.list_blobs(max_results=1))
                        print(f"✅ Can access bucket (listed {len(blobs)} blob(s))")
                    except Exception as list_error:
                        print(f"⚠️  Cannot list bucket contents: {list_error}")
                        print(f"   This might indicate a permissions issue")
                else:
                    print("❌ Bucket is None - storage backend not properly initialized")
                    return False
            else:
                print("⚠️  Storage backend doesn't have 'bucket' attribute")
                # Try to trigger bucket initialization by accessing a property
                try:
                    _ = storage.bucket_name
                    print(f"Bucket name from storage: {_}")
                except Exception as e:
                    print(f"Could not access bucket_name: {e}")
        except Exception as bucket_error:
            print(f"❌ ERROR accessing bucket: {bucket_error}")
            import traceback
            traceback.print_exc()
            return False
        
        # Test upload
        print("\n" + "=" * 60)
        print("Testing File Upload")
        print("=" * 60)
        
        test_content = b"This is a test file for GCS upload verification."
        test_filename = "test/test_upload.txt"
        
        print(f"Uploading test file to: {test_filename}")
        
        # Save file - wrap in try/except to catch actual errors
        try:
            print(f"Attempting to save file...")
            saved_name = storage.save(test_filename, ContentFile(test_content))
            print(f"✅ save() returned: {saved_name}")
        except Exception as save_error:
            print(f"❌ ERROR during save(): {save_error}")
            import traceback
            traceback.print_exc()
            return False
        
        # Verify file exists immediately after save
        print(f"Checking if file exists in storage...")
        try:
            exists = storage.exists(saved_name)
            print(f"storage.exists() returned: {exists}")
            if exists:
                print(f"✅ File exists in storage: {saved_name}")
            else:
                print(f"❌ File does NOT exist in storage: {saved_name}")
                # Try to get more info about why it doesn't exist
                try:
                    # Try to access the bucket directly
                    if hasattr(storage, 'bucket') and storage.bucket:
                        blob = storage.bucket.blob(saved_name)
                        print(f"Checking blob directly...")
                        print(f"Blob exists: {blob.exists()}")
                        if not blob.exists():
                            print(f"Blob path: {saved_name}")
                            print(f"Bucket name: {storage.bucket.name}")
                except Exception as blob_error:
                    print(f"Could not check blob directly: {blob_error}")
                return False
        except Exception as exists_error:
            print(f"❌ ERROR checking if file exists: {exists_error}")
            import traceback
            traceback.print_exc()
            return False
        
        # Get URL
        try:
            file_url = storage.url(saved_name)
            print(f"✅ File URL: {file_url}")
        except Exception as e:
            print(f"⚠️  Could not generate URL: {e}")
        
        # Try to read file back
        try:
            with storage.open(saved_name, 'rb') as f:
                content = f.read()
                if content == test_content:
                    print(f"✅ File content verified correctly")
                else:
                    print(f"⚠️  File content mismatch")
        except Exception as e:
            print(f"❌ Could not read file back: {e}")
            return False
        
        # Cleanup - delete test file
        try:
            storage.delete(saved_name)
            print(f"✅ Test file deleted: {saved_name}")
        except Exception as e:
            print(f"⚠️  Could not delete test file: {e}")
        
        print("\n" + "=" * 60)
        print("✅ All tests passed! GCS is configured correctly.")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_gcs_connection()
    sys.exit(0 if success else 1)

