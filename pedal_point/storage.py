"""
Custom storage backend for Google Cloud Storage with explicit public ACL setting.
"""
from storages.backends.gcloud import GoogleCloudStorage


class PublicGoogleCloudStorage(GoogleCloudStorage):
    """
    Custom GCS storage backend that ensures files are publicly accessible.
    """
    
    def _save(self, name, content):
        """
        Save the file and explicitly set public read ACL.
        """
        # Call parent save method to upload the file
        name = super()._save(name, content)
        
        # Explicitly set public read ACL after upload
        try:
            # Get the blob object using the name (which is the path in the bucket)
            blob = self.bucket.blob(name)
            
            # Check if uniform bucket-level access is enabled
            # If not, we can use ACLs
            try:
                # Try to make the blob publicly readable using ACL
                blob.acl.save_predefined('publicRead')
                print(f"GCS: Set public ACL for {name}")
            except Exception as acl_error:
                # If ACL fails (uniform bucket-level access), try make_public
                print(f"GCS: ACL method failed, trying make_public: {acl_error}")
                try:
                    blob.make_public()
                    print(f"GCS: Made blob public using make_public for {name}")
                except Exception as make_public_error:
                    print(f"WARNING: Both ACL methods failed for {name}: {make_public_error}")
                    
        except Exception as e:
            print(f"WARNING: Failed to set public ACL for {name}: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail the upload if ACL setting fails
            # The file is still saved, just might not be publicly accessible
        
        return name
    
    def url(self, name):
        """
        Return the public URL for the file.
        """
        return super().url(name)

