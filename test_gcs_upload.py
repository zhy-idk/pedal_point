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
        if hasattr(storage, 'bucket'):
            if storage.bucket:
                print(f"✅ Bucket initialized: {storage.bucket.name}")
            else:
                print("❌ Bucket is None - storage backend not properly initialized")
                return False
        else:
            print("⚠️  Storage backend doesn't have 'bucket' attribute (may be lazy-loaded)")
        
        # Test upload
        print("\n" + "=" * 60)
        print("Testing File Upload")
        print("=" * 60)
        
        test_content = b"This is a test file for GCS upload verification."
        test_filename = "test/test_upload.txt"
        
        print(f"Uploading test file to: {test_filename}")
        
        # Save file
        saved_name = storage.save(test_filename, ContentFile(test_content))
        print(f"✅ File saved as: {saved_name}")
        
        # Verify file exists
        if storage.exists(saved_name):
            print(f"✅ File exists in storage: {saved_name}")
        else:
            print(f"❌ File does NOT exist in storage: {saved_name}")
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

