from datetime import datetime

from bson import ObjectId
from fastapi import status, Body, HTTPException
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models import NodeModel, NodeCollection, UpdateNodeModel
from app.database import nodes_collection

router = APIRouter()


def _sanitize_node_dates(node: dict) -> dict:
    """Ensure created_at and updated_at are datetimes (not None)."""
    # created_at
    ca = node.get("created_at")
    if ca is None:
        node["created_at"] = datetime.utcnow()
    elif isinstance(ca, str):
        try:
            node["created_at"] = datetime.fromisoformat(ca)
        except Exception:
            node["created_at"] = datetime.utcnow()

    ua = node.get("updated_at")
    if ua is None:
        node["updated_at"] = datetime.utcnow()
    elif isinstance(ua, str):
        try:
            node["updated_at"] = datetime.fromisoformat(ua)
        except Exception:
            node["updated_at"] = datetime.utcnow()

    return node

@router.get(
    "/nodes/",
    response_description="List all nodes",
    response_model=NodeCollection,
    response_model_by_alias=False
)
async def get_nodes():
    """
    Get all nodes.

    :return: A list of all nodes.
    """

    nodes = await nodes_collection.find().to_list(length=None)
    # sanitize datetime fields so Pydantic validation won't fail
    nodes = [_sanitize_node_dates(n) for n in nodes]
    return NodeCollection(nodes=nodes)


@router.get(
    "/nodes/{node_id}",
    response_description="Get a single node",
    response_model=NodeModel,
    response_model_by_alias=False
)
async def get_node(node_id: str):
    """
    Get a single node by id.

    :param node_id: The id of the node to get.
    :return: The node or a failure message.
    """
    # validate ObjectId
    try:
        oid = ObjectId(node_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid node id: {node_id}")

    node = await nodes_collection.find_one({"_id": oid})
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

    node = _sanitize_node_dates(node)
    return node


@router.get(
    "/nodes/{node_id}/children",
    response_description="Get all children of a node",
    response_model=NodeCollection,
    response_model_by_alias=False
)
async def get_children(node_id: str):
    """
    Get all children of a node by id.

    :param node_id: The id of the node to get children of.
    :return: A list of all children of the node or a failure message.
    """

    async def _get_children(inner_node_id):
        # try to find children where parent_id matches as-stored (string or ObjectId)
        results = await nodes_collection.find({"parent_id": inner_node_id}).to_list(length=None)
        if results:
            return results
        # if nothing found, try treating parent_id as ObjectId
        try:
            oid = ObjectId(inner_node_id)
            results = await nodes_collection.find({"parent_id": oid}).to_list(length=None)
            return results
        except Exception:
            return []

    result = []
    queue = []
    children = await _get_children(node_id)
    queue.extend(children)
    while queue:
        node = queue.pop(0)
        result.append(node)
        children = await _get_children(str(node["_id"]))
        queue.extend(children)
    # sanitize datetimes for all returned nodes
    result = [_sanitize_node_dates(n) for n in result]
    return NodeCollection(nodes=result)


@router.post(
    "/nodes/",
    response_description="Add new node",
    response_model=NodeModel,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def create_node(node: NodeModel = Body(...)):
    """
    Create a new node with a randomly assigned new id.

    :param node: The node to be created.
    :return: The created node or failure message.
    """
    print(node)

    new_node = await nodes_collection.insert_one(node.model_dump(by_alias=True, exclude={"id"}))
    created_node = await nodes_collection.find_one({"_id": new_node.inserted_id})

    return created_node


@router.put(
    "/nodes/{node_id}",
    response_description="Update a node",
    response_model=NodeModel,
    response_model_by_alias=False
)
async def update_node(node_id: str, node: UpdateNodeModel = Body(...)):
    """
    Update a node by id.

    :param node_id: The id of the node to update.
    :param node: The new values for the node.
    :return: The updated node or a failure message.
    """

    node = node.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)

    if node:
        node["updated_at"] = datetime.utcnow()
        updated_node = await nodes_collection.find_one_and_update(
            {"_id": ObjectId(node_id)},
            {"$set": node},
            return_document=True
        )
        if updated_node:
            return updated_node
        else:
            return HTTPException(status_code=404, detail=f"Node {node_id} not found")

    return HTTPException(status_code=400, detail="No values to update")


@router.delete(
    "/nodes/{node_id}",
    response_description="Delete a node"
)
async def delete_node(node_id: str):
    """
    Delete a node by id.

    :param node_id: The id of the node to delete.
    :return: Success or failure message.
    """

    delete_result = await nodes_collection.delete_one({"_id": ObjectId(node_id)})

    if delete_result.deleted_count:
        return JSONResponse("", status_code=204)

    return HTTPException(status_code=404, detail=f"Node {node_id} not found")
