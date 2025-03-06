from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, HTMLResponse
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.exc import SQLAlchemyError
from graphviz import Digraph
from pydantic import BaseModel
from openai import OpenAI
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

environment = "development"  # Change to "production" as needed
engine = create_engine(DATABASE_URL)
metadata = MetaData()
metadata.reflect(bind=engine)

app = FastAPI()
client = OpenAI(api_key=OPENAI_API_KEY)

class SchemaUpdateRequest(BaseModel):
    command: str  # Natural language command from user

async def generate_sql(nl_command: str) -> str:
    prompt = f"Convert this command into SQL: {nl_command}"
    response = client.chat.completions.create(
        model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}]
    )
    print(response)
    return response.choices[0].message.content.strip()

def execute_sql(sql: str):
    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/update-schema")
async def update_schema(request: SchemaUpdateRequest):
    sql = await generate_sql(request.command)
    print(sql)
    execute_sql(sql)
    return {"message": "Schema updated successfully", "sql": sql}

@app.get("/get-schema")
def get_schema():
    # Reflect the schema if it's not already reflected
    metadata.reflect(bind=engine)
    
    schema_info = {}

    for table in metadata.tables.values():
        columns_info = []
        for column in table.columns:
            column_details = {
                "name": column.name,
                "type": str(column.type),  # Data type of the column
                "nullable": column.nullable,
                "default": column.default,
                "primary_key": column.primary_key,
                "unique": column.unique
            }
            columns_info.append(column_details)

        schema_info[table.name] = columns_info

    return schema_info

def generate_schema_graph():
    metadata.reflect(bind=engine)
    dot = Digraph("ERD", format="svg")

    for table in metadata.tables.values():
        dot.node(table.name, shape="box")

        for column in table.columns:
            dot.edge(table.name, f"{table.name}.{column.name}")

    return dot

@app.get("/schema-diagram")
def get_schema_diagram():
    graph = generate_schema_graph()
    svg_data = graph.pipe(format="svg")
    return Response(content=svg_data, media_type="image/svg+xml")


@app.get("/visualize-schema", response_class=HTMLResponse)
async def visualize_schema():
    # Reflect the schema if it's not already reflected
    metadata.reflect(bind=engine)
    
    # Initialize a Graphviz Digraph
    graph = Digraph(format='svg')

    print(metadata.tables)
    # Iterate over all tables and create nodes for each one
    for table in metadata.tables.values():
        # Add table as a node
        graph.node(table.name, table.name, shape="box", style="filled", fillcolor="lightblue")

        # Add columns as nodes
        for column in metadata.tables:
            column_details = table.columns[column]  # Corrected column access
            column_label = f"{column}\nType: {column_details.type}\n"
            column_label += f"Nullable: {column_details.nullable}\n"
            column_label += f"Primary Key: {column_details.primary_key}\n"
            column_label += f"Unique: {column_details.unique}"
            
            # Ensure that the column node name is unique using table name and column name
            graph.node(f"{table.name}_{column}", column_label, shape="ellipse", style="filled", fillcolor="lightyellow")
            
            # Add an edge between the table and its columns
            graph.edge(table.name, f"{table.name}_{column}")

    # Add foreign key relationships
    for table in metadata.tables.values():
        for fkey in table.foreign_keys:
            # Foreign key relationships create edges between columns in different tables
            parent_table = fkey.column.table
            child_column = fkey.column.name
            parent_column = fkey.parent.name

            # Create an edge from the child table's column to the parent table's column
            graph.edge(f"{parent_table.name}_{parent_column}", f"{table.name}_{child_column}", color="red")

    # Render the Graph as SVG
    svg_content = graph.pipe().decode('utf-8')
    
    # Return the SVG as the response
    return svg_content
