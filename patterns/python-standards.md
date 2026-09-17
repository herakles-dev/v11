# Python Code Standards

> Patterns and best practices for Python code in V10 projects.

---

## Type Hints

### Function Signatures

```python
# DO: Type hints on all functions
from typing import Optional, List, Dict

def get_user(user_id: str) -> User:
    """Fetch user by ID."""
    return db.users.find_one({"id": user_id})

def create_user(email: str, name: str, age: Optional[int] = None) -> User:
    """Create a new user."""
    return db.users.insert({
        "email": email,
        "name": name,
        "age": age
    })

# DON'T: Missing type hints
def get_user(user_id):  # BAD
    return db.users.find_one({"id": user_id})
```

### Class Attributes

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class User:
    id: str
    email: str
    name: str
    created_at: datetime
    age: Optional[int] = None

    def is_adult(self) -> bool:
        return self.age is not None and self.age >= 18
```

### Collections

```python
from typing import List, Dict, Set, Tuple

# Lists
def get_user_ids() -> List[str]:
    return ["user1", "user2", "user3"]

# Dictionaries
def get_user_mapping() -> Dict[str, User]:
    return {"user1": User(...), "user2": User(...)}

# Sets
def get_unique_tags() -> Set[str]:
    return {"python", "fastapi", "docker"}

# Tuples (fixed size)
def get_user_name_email(user_id: str) -> Tuple[str, str]:
    user = get_user(user_id)
    return (user.name, user.email)
```

---

## Error Handling

### Custom Exceptions

```python
class NotFoundError(Exception):
    """Resource not found."""
    def __init__(self, message: str, resource_id: str):
        super().__init__(message)
        self.resource_id = resource_id

class ValidationError(Exception):
    """Input validation failed."""
    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.field = field

class DatabaseError(Exception):
    """Database operation failed."""
    pass
```

### Try-Except Pattern

```python
from loguru import logger

async def get_user(user_id: str) -> User:
    """Fetch user by ID with proper error handling."""
    try:
        user = await db.users.find_one({"id": user_id})

        if not user:
            raise NotFoundError(f"User not found", resource_id=user_id)

        return User(**user)

    except NotFoundError:
        raise  # Re-raise known errors

    except Exception as e:
        logger.error(f"Database error fetching user {user_id}: {e}")
        raise DatabaseError(f"Failed to fetch user {user_id}") from e

# DON'T: Bare except
async def get_user(user_id: str) -> Optional[User]:
    try:
        return await db.users.find_one({"id": user_id})
    except:  # BAD: Catches everything, loses error info
        return None
```

### FastAPI Exception Handlers

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    logger.warning(f"Resource not found: {exc.resource_id}")
    return JSONResponse(
        status_code=404,
        content={"error": str(exc), "resource_id": exc.resource_id}
    )

@app.exception_handler(ValidationError)
async def validation_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "field": exc.field}
    )

@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )
```

---

## Async/Await

### Async Functions

```python
import asyncio
from typing import List

# DO: Use async for I/O operations
async def get_user(user_id: str) -> User:
    user = await db.users.find_one({"id": user_id})
    return User(**user)

async def process_user(user_id: str) -> None:
    user = await get_user(user_id)
    enriched = await enrich_user_data(user)
    await db.users.update_one({"id": user_id}, enriched)

# DON'T: Forget await
async def process_user(user_id: str) -> None:
    user = get_user(user_id)  # BAD: Returns coroutine, not User
    print(user)  # Prints <coroutine object>
```

### Parallel Execution

```python
# Sequential (slow)
user = await get_user(user_id)
posts = await get_posts(user_id)
comments = await get_comments(user_id)

# Parallel (fast)
user, posts, comments = await asyncio.gather(
    get_user(user_id),
    get_posts(user_id),
    get_comments(user_id)
)

# Parallel with error handling
results = await asyncio.gather(
    get_user(user_id),
    get_posts(user_id),
    get_comments(user_id),
    return_exceptions=True  # Don't fail on first error
)

for i, result in enumerate(results):
    if isinstance(result, Exception):
        logger.error(f"Task {i} failed: {result}")
```

---

## Validation (Pydantic)

### Request Models

```python
from pydantic import BaseModel, EmailStr, Field, validator

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    age: Optional[int] = Field(None, ge=0, le=150)

    @validator('password')
    def validate_password(cls, v):
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        return v

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True  # For SQLAlchemy models
```

### Usage in FastAPI

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.post("/users", response_model=UserResponse)
async def create_user(request: CreateUserRequest):
    # Request is automatically validated
    user = await db.users.create(
        email=request.email,
        password_hash=hash_password(request.password),
        name=request.name,
        age=request.age
    )

    return UserResponse(**user.dict())
```

---

## Docstrings

### Google Style

```python
def get_user(user_id: str, include_posts: bool = False) -> User:
    """Fetch user by ID.

    Args:
        user_id: The unique identifier for the user.
        include_posts: Whether to include user posts. Defaults to False.

    Returns:
        User object with all user data.

    Raises:
        NotFoundError: If user does not exist.
        DatabaseError: If database query fails.

    Example:
        >>> user = get_user("user123")
        >>> print(user.email)
        'user@example.com'
    """
    # Implementation
```

### Class Docstrings

```python
class UserService:
    """Service for managing user operations.

    This service handles user CRUD operations, authentication,
    and user data enrichment.

    Attributes:
        db: Database connection instance.
        cache: Redis cache instance.

    Example:
        >>> service = UserService(db, cache)
        >>> user = await service.get_user("user123")
    """

    def __init__(self, db: Database, cache: Redis):
        self.db = db
        self.cache = cache
```

---

## Naming Conventions

```python
# Variables: snake_case
user_id = "123"
is_admin = True
created_at = datetime.now()

# Constants: UPPER_SNAKE_CASE
MAX_RETRIES = 3
API_BASE_URL = "https://api.example.com"
JWT_EXPIRATION_HOURS = 24

# Functions: snake_case
def get_user_by_id(user_id: str) -> User:
    pass

async def create_user_async(data: dict) -> User:
    pass

# Classes: PascalCase
class User:
    pass

class UserService:
    pass

class DatabaseConnection:
    pass

# Private attributes/methods: _leading_underscore
class User:
    def __init__(self):
        self._password_hash = None  # Private

    def _internal_method(self):  # Private method
        pass
```

---

## File Organization

```
src/
├── models/
│   ├── __init__.py
│   ├── user.py          # User Pydantic models
│   └── auth.py          # Auth Pydantic models
├── routes/
│   ├── __init__.py
│   ├── users.py         # User endpoints
│   └── auth.py          # Auth endpoints
├── services/
│   ├── __init__.py
│   ├── user_service.py  # Business logic
│   └── auth_service.py
├── db/
│   ├── __init__.py
│   └── connection.py    # Database setup
└── utils/
    ├── __init__.py
    ├── logger.py        # Logging utility
    └── security.py      # Password hashing, etc.
```

---

## Import Patterns

```python
# DO: Group imports
# 1. Standard library
import os
from datetime import datetime
from typing import List, Optional

# 2. Third-party libraries
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from loguru import logger

# 3. Local modules
from models.user import User, CreateUserRequest
from services.user_service import UserService
from utils.logger import setup_logger

# DON'T: Mixed order
from models.user import User
import os
from fastapi import FastAPI
from typing import List
```

---

## SQL Injection Prevention

```python
# DO: Parameterized queries
async def get_user(user_id: str) -> User:
    query = "SELECT * FROM users WHERE id = %s"
    result = await db.fetch_one(query, user_id)
    return User(**result)

# DON'T: String interpolation (SQL INJECTION!)
async def get_user(user_id: str) -> User:
    query = f"SELECT * FROM users WHERE id = {user_id}"  # DANGEROUS!
    result = await db.fetch_one(query)
    return User(**result)

# DON'T: String concatenation (SQL INJECTION!)
async def get_user(user_id: str) -> User:
    query = "SELECT * FROM users WHERE id = " + user_id  # DANGEROUS!
    result = await db.fetch_one(query)
    return User(**result)
```

---

## Video Processing Standards

> Patterns from ArchiveStream service (reference implementation at `/path/to/operator-home/archivestream-service`)

### FFmpeg Best Practices

**Always prefer stream copy when possible:**

```python
# Check if re-encoding is needed
def process_video(input_path: str, output_path: str) -> None:
    """Process video with minimal quality loss."""

    # Analyze input codec
    probe = ffmpeg.probe(input_path)
    video_stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    current_codec = video_stream['codec_name']

    if current_codec in ("h264", "avc1") and format_compatible:
        # Stream copy (zero quality loss, 99% faster)
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "copy",  # No re-encoding
            "-c:a", "copy",
            output_path
        ]
    else:
        # Re-encode only when necessary
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-c:v", "h264_nvenc",  # Try GPU encoding first
            "-preset", "fast",
            "-crf", "18",
            output_path
        ]

    subprocess.run(cmd, check=True)
```

**Enable multi-threading:**

```python
def build_ffmpeg_command(input_path: str, output_path: str, quality: str = "high") -> List[str]:
    """Build FFmpeg command with performance optimizations."""

    cmd = [
        "ffmpeg",
        "-threads", "0",  # Auto-detect CPU cores (+30% speed)
        "-i", input_path,
    ]

    # Quality presets
    if quality == "high":
        cmd.extend(["-c:v", "libx264", "-preset", "slow", "-crf", "16"])
    elif quality == "good":
        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "20"])
    else:  # fast
        cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"])

    cmd.append(output_path)
    return cmd
```

**Quality settings reference:**

| CRF Value | Use Case | File Size | Speed |
|-----------|----------|-----------|-------|
| 16-18 | High quality preprocessing | Large | Slow |
| 20-23 | Good quality output | Medium | Fast |
| 24-28 | Quick preview/draft | Small | Very fast |

**Preset reference:**

- `ultrafast` - Fastest encoding, largest files
- `veryfast` - Good speed/size balance
- `fast` - Default for most workflows
- `medium` - FFmpeg default
- `slow` - Better compression, slower encoding
- `veryslow` - Best compression, very slow

### Frame Count Validation

**Pattern for diffusion models requiring specific frame counts:**

```python
def validate_frame_count(num_frames: int, model_constraint: str = "4n+1") -> int:
    """Validate and adjust frame count for model requirements.

    Args:
        num_frames: Requested number of frames.
        model_constraint: Frame count rule ("4n+1", "8n+1", etc.).

    Returns:
        Adjusted frame count meeting constraint.

    Example:
        >>> validate_frame_count(30, "4n+1")
        29  # (29-1)//4 = 7, 7*4+1 = 29
    """
    if model_constraint == "4n+1":
        # Ditto model requires frames = 4n+1
        return ((num_frames - 1) // 4) * 4 + 1
    elif model_constraint == "8n+1":
        return ((num_frames - 1) // 8) * 8 + 1

    return num_frames

# Usage in video-to-video pipeline
frames = extract_frames(video_path)
num_frames = validate_frame_count(len(frames), "4n+1")
frames = frames[:num_frames]  # Trim to valid count
```

**Gotchas:**
- Diffusion models may crash with invalid frame counts (not just poor output)
- Always validate BEFORE loading into GPU memory
- Document frame constraints in API/UI ("Ditto: 4n+1 frames")

---

## ML Dependency Management

> Critical patterns for PyTorch/transformers projects

### Version Constraints

**Always pin NumPy <2.0 for torch compatibility:**

```python
# requirements.txt
numpy<2.0              # REQUIRED for scipy/sklearn compatibility
torch>=2.0.0
torchvision>=0.15.0
opencv-python-headless<4.10  # Stability (4.10+ has breaking changes)
diffusers>=0.28.0
transformers>=4.40.0
```

**Why these constraints matter:**

| Constraint | Reason | Impact if violated |
|------------|--------|-------------------|
| `numpy<2.0` | torch compiled against 1.x ABI | scipy/sklearn import crashes |
| `opencv<4.10` | 4.10 changed numpy array handling | Video read failures |
| `diffusers>=0.28` | Pipeline API changes in 0.28+ | AttributeError on pipeline methods |

### Graceful Optional Dependencies

**Pattern for optional performance libraries:**

```python
# Try to import optimization, fall back gracefully
try:
    from optimum.quanto import quantize, freeze
    QUANTO_AVAILABLE = True
except ImportError:
    QUANTO_AVAILABLE = False
    print("Warning: optimum-quanto not available, quantization disabled")

try:
    import xformers
    XFORMERS_AVAILABLE = True
except ImportError:
    XFORMERS_AVAILABLE = False
    print("Warning: xformers not available, using standard attention")

# Later in code
def load_model(use_optimization: bool = True) -> torch.nn.Module:
    """Load model with optional optimizations."""
    model = load_base_model()

    if use_optimization and QUANTO_AVAILABLE:
        try:
            quantize(model, weights=qint8)
            freeze(model)
            print("Applied INT8 quantization (2x memory reduction)")
        except Exception as e:
            logger.warning(f"Quantization failed: {e}, using full precision")

    if XFORMERS_AVAILABLE:
        model.enable_xformers_memory_efficient_attention()

    return model
```

**Benefits:**
- No crashes from missing optional deps
- Clear user communication about missing features
- Robust fallback behavior
- Easy to test with/without optimizations

### Hugging Face Model Download Patterns

**Efficient model caching:**

```python
from huggingface_hub import snapshot_download
from pathlib import Path

def download_model(model_id: str, cache_dir: str = "~/.cache/huggingface") -> Path:
    """Download HF model with progress tracking.

    Args:
        model_id: Hugging Face model ID (e.g., "Wan-AI/Wan2.1-VACE-14B-diffusers").
        cache_dir: Local cache directory.

    Returns:
        Path to downloaded model directory.
    """
    cache_path = Path(cache_dir).expanduser()

    model_path = snapshot_download(
        repo_id=model_id,
        cache_dir=cache_path,
        local_files_only=False,  # Download if not cached
        resume_download=True,    # Resume interrupted downloads
        ignore_patterns=["*.msgpack", "*.h5"],  # Skip unnecessary formats
    )

    return Path(model_path)

# Usage
model_path = download_model("Wan-AI/Wan2.2-T2V-A14B-Diffusers")
pipeline = WanVideoToVideoPipeline.from_pretrained(model_path)
```

**Gotchas:**
- Must use `-diffusers` suffix repos for pipeline compatibility
- `snapshot_download` returns string path, wrap in `Path()` for consistency
- Set `local_files_only=True` for air-gapped deployment

---

## GPU Memory Management

> Patterns for VRAM-constrained ML workloads

### VRAM-Adaptive Batching

```python
import torch

def get_optimal_batch_size(model_size_gb: float = 14) -> int:
    """Calculate batch size based on available VRAM.

    Args:
        model_size_gb: Model memory footprint in GB.

    Returns:
        Recommended batch size.
    """
    if not torch.cuda.is_available():
        return 1

    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3

    # Conservative multipliers prevent OOM
    # Formula: (VRAM - model_size) / memory_per_sample
    if vram_gb >= 96:
        return 160
    elif vram_gb >= 80:
        return 128
    elif vram_gb >= 48:
        return 81
    elif vram_gb >= 24:
        return 32
    else:
        return 16

# Usage
batch_size = get_optimal_batch_size(model_size_gb=14)
dataloader = DataLoader(dataset, batch_size=batch_size)
```

### Memory Cleanup Between Jobs

```python
def cleanup_gpu_memory() -> None:
    """Release GPU memory after processing job."""
    import gc

    # Clear Python garbage
    gc.collect()

    # Clear CUDA cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

        # Reset peak memory stats (for monitoring)
        if hasattr(torch.cuda, 'reset_peak_memory_stats'):
            torch.cuda.reset_peak_memory_stats()

# Usage in worker loop
def process_job(job_id: str) -> None:
    try:
        model = load_model()
        result = model.process(job_id)
        save_result(result)
    finally:
        # ALWAYS cleanup, even on error
        del model
        cleanup_gpu_memory()
```

### Model Offloading Patterns

```python
from accelerate import cpu_offload

def load_large_model(model_id: str, enable_offloading: bool = True):
    """Load model with CPU offloading for VRAM efficiency.

    CPU offloading moves inactive layers to RAM, reducing VRAM usage by 40-60%.
    """
    from diffusers import WanVideoToVideoPipeline

    pipeline = WanVideoToVideoPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16,  # Half precision (2x memory savings)
    )

    if enable_offloading and torch.cuda.is_available():
        # Move model components to CPU when idle
        pipeline.enable_model_cpu_offload()
        print("CPU offloading enabled (expect 15% slower, 50% less VRAM)")
    else:
        pipeline.to("cuda")

    return pipeline
```

**Memory comparison:**

| Configuration | 14B Model VRAM | Speed | Use Case |
|---------------|----------------|-------|----------|
| Full precision FP32 | 56 GB | 1.0x | Not recommended |
| Half precision FP16 | 28 GB | 1.0x | Standard |
| FP16 + CPU offload | 14 GB | 0.85x | VRAM-constrained |
| INT8 quantization | 14 GB | 1.2x | Production (requires quanto) |

**Gotchas:**
- CPU offloading adds 10-20% latency (data transfer overhead)
- Quantization may reduce output quality (test before production)
- `enable_model_cpu_offload()` requires accelerate>=0.20.0

---

*Python standards for V10 projects*
