# Loading Overlay - Timing & Performance Tracking

## Overview

The PyPondo loading overlay now automatically tracks and displays execution times for all operations. Users can see:
- **Elapsed Time**: How long the current operation has been running
- **Response Time**: Server-side execution time (if available)
- **Completion Time**: How long an operation took once finished

## Frontend Features

### Automatic Timing Display

The loading overlay shows elapsed time in real-time for any operation:

```
Please wait while the action completes...
Elapsed: 2s 340ms
```

### Built-in Functions

Three JavaScript functions are available:

#### 1. `pypondoShowLoading(text)`
Shows loading spinner with custom message and starts timing
```javascript
window.pypondoShowLoading('Processing payment...');
// Shows: "Processing payment... Elapsed: X s"
```

#### 2. `pypondoHideLoading()`
Hides the overlay and stops the timer
```javascript
window.pypondoHideLoading();
```

#### 3. `pypondoShowLoadingWithTime(text, responseTimeMs)`
Shows final timing once operation completes
```javascript
window.pypondoShowLoadingWithTime('Operation completed', 1234);
// Shows: "Operation completed... Completed in 1s 234ms"
```

## Backend Timing

### Automatic Response Header

The backend automatically adds execution time to response headers:

```
X-Response-Time: 1234
```

(Time in milliseconds)

### Using the Timing Decorator

To track function execution time on the backend, import and use the `track_execution_time` decorator:

```python
from app import track_execution_time

@app.route('/api/expensive-operation', methods=['POST'])
@track_execution_time
def expensive_operation():
    # Your code here
    return jsonify({'result': 'success'})
```

The decorator will:
- Measure execution time
- Add `X-Response-Time` header to response
- Handle both regular responses and redirects

### Example: Booking Route

```python
@app.route('/book', methods=['POST'])
@track_execution_time
@login_required
def book_pc():
    # Booking logic
    return redirect(url_for('bookings'))
```

## How It Works

### Timeline

1. User clicks button/form/link
2. Loading overlay appears with "Elapsed: 0s"
3. Timer updates every 500ms
4. Request sent to backend (with timing decorator)
5. Response received with `X-Response-Time` header
6. Frontend displays completion time
7. Overlay hides after 2 seconds

### Example Flow

```
User clicks "Reserve PC"
↓
Loading starts: "Elapsed: 0s"
↓
Elapsed: 0s, 1s, 2s... (updates every 500ms)
↓
Server responds with X-Response-Time: 1250
↓
"Reserve successful! Completed in 1s 250ms"
↓
(Overlay hides after 2 seconds)
```

## For Developers

### Add Timing to Any Action

1. **Slow Endpoint** - Add decorator:
   ```python
   @track_execution_time
   ```

2. **Custom JS Timing** - In your templates:
   ```javascript
   // Start timing
   window.pypondoShowLoading('Custom operation...');
   
   // When done
   window.pypondoShowLoadingWithTime('Done!', 5000);
   ```

3. **Monitor Performance** - Check:
   - Frontend: Elapsed time displayed in overlay
   - Backend: Check `X-Response-Time` headers in browser DevTools
   - Database: Add timing for DB queries if needed

### Disable for Specific Elements

```html
<!-- Skip loading overlay for this link -->
<a href="/page" data-no-loading>Direct Link</a>

<!-- Skip for this button -->
<button data-no-loading>Skip Loading</button>
```

## Browser DevTools

### Check Response Times

1. Open DevTools (F12)
2. Go to Network tab
3. Look for `X-Response-Time` header in responses
4. Times shown in milliseconds

### Performance Example

```
Request: /book
Headers > Response:
X-Response-Time: 523   ← Time in ms
```

## Notes

- Timer updates every 500ms for performance
- All times are in milliseconds then converted to human-readable format
- Timing includes network latency + server execution + database queries
- Very fast operations may show "Completed in 0s"
- Test with slow network (DevTools throttling) to see realistic times
