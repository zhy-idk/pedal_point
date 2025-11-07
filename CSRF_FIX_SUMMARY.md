# CSRF 403 Error Fix - Summary

## Problem
Getting "403 CSRF verification failed" when trying to login from Render frontend but not from local frontend.

## Root Causes Identified

### 1. Invalid Cookie Domain Settings
**Before:**
```python
SESSION_COOKIE_DOMAIN = DOMAIN  # Was set to env variable
CSRF_COOKIE_DOMAIN = DOMAIN     # Was set to env variable
```

**After:**
```python
SESSION_COOKIE_DOMAIN = None  # Must be None for cross-origin
CSRF_COOKIE_DOMAIN = None     # Must be None for cross-origin
```

**Why:** For cross-origin authentication to work, cookies must not have a domain restriction. Setting to `None` allows the browser to handle domain logic correctly.

---

### 2. Invalid Wildcard Patterns in CSRF_TRUSTED_ORIGINS
**Before:**
```python
CSRF_TRUSTED_ORIGINS = [
    "http://*:5173",  # INVALID - Django doesn't support wildcards
    "http://*:3000",  # INVALID
    # ...
]
```

**After:**
```python
CSRF_TRUSTED_ORIGINS = [
    # Local development
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    # Production URLs
    "https://pedalpoint-frontend.onrender.com",
    "https://pedal-point.onrender.com",
]
```

**Why:** Django's `CSRF_TRUSTED_ORIGINS` doesn't support wildcard patterns. Invalid entries are silently ignored, causing CSRF validation to fail.

---

### 3. Missing Proxy SSL Header Configuration
**Before:** Not configured

**After:**
```python
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
```

**Why:** Render (and other reverse proxies) terminate SSL at the proxy level. Without this setting, Django thinks all requests are HTTP, causing CSRF validation issues with HTTPS origins.

---

### 4. Added Explicit CSRF Configuration
**Added:**
```python
CSRF_COOKIE_NAME = "csrftoken"
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
CSRF_COOKIE_AGE = 31449600  # 1 year
CSRF_USE_SESSIONS = False
```

**Why:** Explicit configuration ensures consistent behavior across environments and makes debugging easier.

---

## Deployment Checklist

### 1. Environment Variables
Make sure these are set in your Render environment:
- `IS_PRODUCTION=True`
- `BACKEND_URL=https://pedal-point.onrender.com`
- `FRONTEND_URL=https://pedalpoint-frontend.onrender.com`
- `DOMAIN=None` (or don't set it at all)

### 2. Run Site Domain Update Command
After deploying, run this command on Render:
```bash
python manage.py update_site_domain --domain pedal-point.onrender.com
```

This ensures django-allauth generates correct OAuth callback URLs.

### 3. Update Google OAuth Console
Make sure your Google Cloud Console has these **exact** redirect URIs:
- `https://pedal-point.onrender.com/accounts/google/login/callback/`

### 4. Update Facebook App Settings (if using)
- `https://pedal-point.onrender.com/accounts/facebook/login/callback/`

### 5. Verify CORS Configuration
Ensure frontend URL is in `CORS_ALLOWED_ORIGINS`:
```python
CORS_ALLOWED_ORIGINS = [
    "https://pedalpoint-frontend.onrender.com",
]
```

---

## Testing After Deployment

1. **Clear browser cache and cookies** (important!)
2. **Open browser DevTools → Network tab**
3. **Navigate to login page**
4. **Check CSRF token is received:**
   - Look for request to `/api/csrf/`
   - Should return 200 with `csrfToken` in response
5. **Check CSRF token is sent:**
   - Look for login request
   - Should have header: `X-CSRFToken: <token>`
6. **Check cookies:**
   - Should see `csrftoken` cookie
   - Should see `sessionid` cookie
   - Both should have `SameSite=None; Secure` in production

---

## Debugging CSRF Issues

If you still get 403 errors, check these in browser DevTools:

### Console Logs
Your frontend logs CSRF token operations:
```
[CSRF] Token from meta tag, length: XX
[API] Sending CSRF token for /auth/login
```

### Network Tab - Check Request Headers
```
X-CSRFToken: <should be present>
Origin: https://pedalpoint-frontend.onrender.com
Referer: https://pedalpoint-frontend.onrender.com/login
Cookie: csrftoken=...; sessionid=...
```

### Network Tab - Check Response Headers
```
Set-Cookie: csrftoken=...; SameSite=None; Secure; Path=/
Set-Cookie: sessionid=...; SameSite=None; Secure; Path=/; HttpOnly
Access-Control-Allow-Origin: https://pedalpoint-frontend.onrender.com
Access-Control-Allow-Credentials: true
```

---

## Common Issues

### Issue: Cookie not being set
**Solution:** Check `CSRF_COOKIE_SECURE` is `True` in production and frontend is using HTTPS.

### Issue: Cookie set but not sent
**Solution:** 
- Check `SameSite=None` and `Secure=True` are set
- Verify `withCredentials: true` in axios config
- Verify CORS is configured correctly

### Issue: Token sent but still 403
**Solution:**
- Check `CSRF_TRUSTED_ORIGINS` has exact frontend URL
- Check `SECURE_PROXY_SSL_HEADER` is set
- Check Django Site domain is correct: `python manage.py update_site_domain`

---

## Files Modified
- `pedal_point/pedal_point/settings.py`
- `pedal_point/api/management/commands/update_site_domain.py` (new file)

## Related Documentation
- Django CSRF: https://docs.djangoproject.com/en/stable/ref/csrf/
- Django CORS: https://github.com/adamchainz/django-cors-headers
- Render Deployment: https://render.com/docs/deploy-django

