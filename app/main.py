import os
import json
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.database import db
from app.endpoints.nodes import router as nodes_router
from app.models import NodeModel
from app.utils import NodeType
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

class Config:
    """Application configuration"""
    CORS_ORIGINS = ["*"]
    CONFIGURATIONS_DIR = Path("./configurations")
    LOG_NAME = "fire-configuration"

config = Config()

app = FastAPI(
    title="Fire Configuration API",
    description="API for managing configuration nodes",
    version="1.0.0"
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
    try:
        json.loads(content)
        return True
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filename}: {e}")
        return False

async def create_root_node() -> str:
    try:
        nodes = db.get_collection("nodes")
        root_node = NodeModel(
            name="root",
            node_type=NodeType.DIR,
            data="",
            parent_id=None
        )
        
        root_result = await nodes.insert_one(
            root_node.model_dump(by_alias=True, exclude={"id"})
        )
        
        root_id = str(root_result.inserted_id)
        logger.info(f"Root node created with ID: {root_id}")
        return root_id
        
    except Exception as e:
        logger.error(f"Failed to create root node: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize database")

async def load_configuration_file(json_file: Path, root_id: str) -> bool:
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not validate_json_content(content, json_file.name):
            return False
        
        nodes = db.get_collection("nodes")
        file_node = NodeModel(
            name=json_file.name,
            node_type=NodeType.FILE,
            data=content,
            parent_id=root_id
        )
        
        await nodes.insert_one(
            file_node.model_dump(by_alias=True, exclude={"id"})
        )
        
        logger.info(f"Loaded configuration: {json_file.name} ({len(content)} characters)")
        return True
        
    except Exception as e:
        logger.error(f"Error loading {json_file}: {e}")
        return False

async def load_configuration_files(root_id: str) -> int:
    if not config.CONFIGURATIONS_DIR.exists():
        logger.warning(f"Configurations directory does not exist: {config.CONFIGURATIONS_DIR}")
        return 0
    
    if not config.CONFIGURATIONS_DIR.is_dir():
        logger.warning(f"Configurations path is not a directory: {config.CONFIGURATIONS_DIR}")
        return 0
    
    json_files = list(config.CONFIGURATIONS_DIR.glob("*.json"))
    
    if not json_files:
        logger.info("No JSON files found in configurations directory")
        return 0
    
    logger.info(f"Loading configuration files from: {config.CONFIGURATIONS_DIR}")
    
    loaded_count = 0
    for json_file in sorted(json_files):
        if await load_configuration_file(json_file, root_id):
            loaded_count += 1
    
    logger.info(f"Successfully loaded {loaded_count} out of {len(json_files)} configuration files")
    return loaded_count

async def initialize_database() -> None:
    """Initialize the database with root node and configuration files"""
    try:
        nodes = db.get_collection("nodes")
        existing_element = await nodes.find_one()
        
        if existing_element:
            logger.info("Database already initialized, skipping...")
            return
        
        logger.info("Initializing database...")        
        root_id = await create_root_node()
        
        await load_configuration_files(root_id)
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

@app.on_event("startup")
async def startup_event():
    """Application startup event handler"""
    setup_logging(config.LOG_NAME)
    await initialize_database()

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event handler"""
    logger.info("Application shutting down...")

setup_cors_middleware()
app.include_router(nodes_router, prefix="/api/v1", tags=["nodes"])

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "Fire Configuration API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)