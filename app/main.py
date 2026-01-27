import os
import json
import logging
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi import Body
from fastapi.middleware.cors import CORSMiddleware

from app.database import db
from app.endpoints.nodes import router as nodes_router
from app.models import NodeModel
from app.utils import NodeType
from app.logging_config import setup_logging

from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class Config:
    """Application configuration"""
    CORS_ORIGINS = ["*"]
    CONFIGURATIONS_DIRS = [Path("./cracow"), Path("./forest")]
    LOG_NAME = "fire-configuration"

config = Config()

# Initialize logging at module level
setup_logging(config.LOG_NAME)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    logger.info("Starting application lifespan, initializing database...")
    try:
        await initialize_database()
    except Exception as e:
        logger.exception("Error during database initialization: %s", e)
    
    yield
    
    logger.info("Application shutting down...")

app = FastAPI(
    title="Fire Configuration API",
    description="API for managing configuration nodes",
    version="1.0.0",
    lifespan=lifespan
)

def setup_cors_middleware() -> None:
    """Configure CORS middleware"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def validate_json_content(content: str, filename: str) -> bool:
    """Validate file content is valid JSON. Return True when ok, False otherwise."""
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", filename, e)
        return False


async def wait_for_mongo(timeout: int = 30, interval: float = 2.0) -> bool:
    """Wait until MongoDB responds to a ping. Returns True if available within timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Use motor async API directly instead of run_in_executor to avoid event loop issues
            await db.client.admin.command("ping")
            logger.info("MongoDB available")
            return True
        except asyncio.CancelledError:
            logger.info("wait_for_mongo was cancelled")
            return False
        except Exception as e:
            logger.warning("MongoDB not available: %s; retrying in %s s", e, interval)
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("sleep in wait_for_mongo cancelled")
                return False
    return False


async def create_root_node() -> str:
    """Create a root node in the DB and return its id."""
    try:
        nodes = db.get_collection("nodes")
        existing = await nodes.find_one({"name": "root", "parent_id": None})
        if existing:
            root_id = str(existing.get("_id"))
            logger.info("Found existing root node with ID: %s", root_id)
            return root_id

        root_node = {
            "name": "root",
            "node_type": int(NodeType.DIR),
            "data": None,
            "parent_id": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        result = await nodes.insert_one(root_node)
        root_id = str(result.inserted_id)
        logger.info("Root node created with ID: %s", root_id)
        return root_id
    except Exception as e:
        logger.exception("Failed to create root node: %s", e)
        raise HTTPException(status_code=500, detail="Failed to initialize database")

async def load_configuration_file(json_file: Path, root_id: str) -> bool:
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if not validate_json_content(content, json_file.name):
            return False

        nodes = db.get_collection("nodes")
        filter_doc = {"name": json_file.name, "parent_id": root_id}
        now = datetime.utcnow()
        update_doc = {
            "$set": {
                "name": json_file.name,
                "node_type": int(NodeType.FILE),
                "parent_id": root_id,
                "data": content,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now
            }
        }
        await nodes.update_one(filter_doc, update_doc, upsert=True)
        logger.info("Upserted configuration: %s (%d characters)", json_file.name, len(content))
        return True
    except Exception as e:
        logger.exception("Error loading %s: %s", json_file, e)
        return False

async def create_folder_node(name: str, parent_id: str) -> str:
    """Create a folder node if it doesn't exist and return its ID."""
    nodes = db.get_collection("nodes")
    existing = await nodes.find_one({"name": name, "parent_id": parent_id, "node_type": int(NodeType.DIR)})
    if existing:
        return str(existing["_id"])
    
    now = datetime.utcnow()
    folder_node = {
        "name": name,
        "node_type": int(NodeType.DIR),
        "data": None,
        "parent_id": parent_id,
        "created_at": now,
        "updated_at": now,
    }
    result = await nodes.insert_one(folder_node)
    return str(result.inserted_id)

async def load_configuration_files(workspace_id: str) -> int:
    total_loaded = 0
    for config_dir in config.CONFIGURATIONS_DIRS:
        if not config_dir.exists() or not config_dir.is_dir():
            logger.warning("Configurations directory does not exist or is not a directory: %s", config_dir)
            continue

        # Create subfolder in DB matching the physical folder name
        folder_id = await create_folder_node(config_dir.name, workspace_id)
        
        json_files = list(config_dir.glob("*.json"))
        if not json_files:
            logger.info("No JSON files found in configurations directory: %s", config_dir)
            continue

        logger.info("Loading configuration files from: %s into DB folder: %s", config_dir, config_dir.name)

        loaded_count = 0
        for json_file in sorted(json_files):
            # Load file into its respective folder
            if await load_configuration_file(json_file, folder_id):
                loaded_count += 1
        
        total_loaded += loaded_count
        logger.info("Successfully loaded %d out of %d configuration files from %s", loaded_count, len(json_files), config_dir)

    return total_loaded

async def create_workspace_and_settings_folders(root_id: str) -> None:
    """Create settings folder under root if it doesn't exist."""
    nodes = db.get_collection("nodes")
    now = datetime.utcnow()
    
    # Create settings folder
    settings_filter = {"name": "settings", "parent_id": root_id}
    settings_doc = await nodes.find_one(settings_filter)
    if not settings_doc:
        settings_node = {
            "name": "settings",
            "node_type": int(NodeType.DIR),
            "data": None,
            "parent_id": root_id,
            "created_at": now,
            "updated_at": now,
        }
        result = await nodes.insert_one(settings_node)
        settings_id = str(result.inserted_id)
        logger.info("Created settings folder under root")
    else:
        settings_id = str(settings_doc["_id"])
    
    # Create sim_settings file in settings folder if it doesn't exist
    sim_settings_filter = {"name": "sim_settings", "parent_id": settings_id}
    sim_settings_exists = await nodes.find_one(sim_settings_filter)
    if not sim_settings_exists:
        sim_settings_node = {
            "name": "sim_settings",
            "node_type": int(NodeType.FILE),
            "data": "{}",
            "parent_id": settings_id,
            "created_at": now,
            "updated_at": now,
        }
        await nodes.insert_one(sim_settings_node)
        logger.info("Created sim_settings file in settings folder")


async def initialize_database() -> None:
    """Initialize the database with root node and configuration files."""
    try:
        timeout = int(os.getenv("MONGO_STARTUP_TIMEOUT", "30"))
        try:
            mongo_ok = await wait_for_mongo(timeout=timeout)
        except asyncio.CancelledError:
            logger.info("initialize_database cancelled while waiting for Mongo")
            return
        if not mongo_ok:
            logger.error("MongoDB not reachable after %s seconds, skipping DB initialization", timeout)
            return

        nodes = db.get_collection("nodes")
        
        logger.info("Initializing database...")
        root_id = await create_root_node()
        await create_workspace_and_settings_folders(root_id)
        
        # Load configuration files directly under root
        await load_configuration_files(root_id)
        
        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
        # Do not raise, allow app to start in degraded mode
        return


setup_cors_middleware()
app.include_router(nodes_router, prefix="/api/v1", tags=["nodes"])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Fire Configuration API is running"}


@app.post("/admin/reload-configs")
async def admin_reload_configs(force: bool = False):
    """Admin endpoint to reload configuration files from disk.

    If `force` is true, the `nodes` collection will be cleared before import.
    This is destructive and should be protected in production.
    """
    nodes = db.get_collection("nodes")
    if force:
        logger.warning("Force reload requested: deleting all documents from nodes collection")
        await nodes.delete_many({})

    root_id = await create_root_node()
    await create_workspace_and_settings_folders(root_id)
    
    # Load configuration files directly under root
    loaded = await load_configuration_files(root_id)
    return {"loaded": loaded}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
