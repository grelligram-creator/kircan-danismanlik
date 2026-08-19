# Auth Testing Playbook (Emergent Google Auth)

## Test User Setup (mongosh)
```
mongosh --eval "
use('test_database');
db.users.updateOne(
  { user_id: 'test-user-seed-001' },
  { \$set: { user_id: 'test-user-seed-001', email: 'test.valuer@example.com', name: 'Test Valuer', picture: '', credits: 500, created_at: new Date() } },
  { upsert: true }
);
db.user_sessions.updateOne(
  { session_token: 'test_session_seed_001' },
  { \$set: { user_id: 'test-user-seed-001', session_token: 'test_session_seed_001', expires_at: new Date(Date.now() + 7*24*60*60*1000), created_at: new Date() } },
  { upsert: true }
);
"
```

## Backend curl test
```
curl -X GET "$REACT_APP_BACKEND_URL/api/auth/me" \
  -H "Authorization: Bearer test_session_seed_001"
```

## Browser cookie injection
```javascript
await page.context.add_cookies([{
    "name": "session_token",
    "value": "test_session_seed_001",
    "domain": "realestate-ai-flow.preview.emergentagent.com",
    "path": "/",
    "httpOnly": true,
    "secure": true,
    "sameSite": "None"
}]);
```
