"""
Databricks Connection and Table Creation Script

This script demonstrates how to:
1. Connect to Databricks using databricks-sql-connector
2. Create a schema (if not exists)
3. Create a table within the schema
4. Perform basic operations

Requirements:
    pip install databricks-sql-connector python-dotenv
"""

import os
import sys
from datetime import datetime
from databricks import sql
from dotenv import load_dotenv


class DatabricksManager:
    """Manages Databricks connections and operations"""
    
    def __init__(self):
        """Initialize connection parameters from environment variables"""
        load_dotenv()
        
        self.server_hostname = os.getenv('DATABRICKS_SERVER_HOSTNAME')
        self.http_path = os.getenv('DATABRICKS_HTTP_PATH')
        self.access_token = os.getenv('DATABRICKS_ACCESS_TOKEN')
        self.catalog = os.getenv('DATABRICKS_CATALOG', 'hive_metastore')
        
        self.connection = None
        self.cursor = None
        
        self._validate_credentials()
    
    def _validate_credentials(self):
        """Validate that all required credentials are present"""
        missing = []
        if not self.server_hostname:
            missing.append('DATABRICKS_SERVER_HOSTNAME')
        if not self.http_path:
            missing.append('DATABRICKS_HTTP_PATH')
        if not self.access_token:
            missing.append('DATABRICKS_ACCESS_TOKEN')
        
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Please create a .env file with your Databricks credentials."
            )
    
    def connect(self):
        """Establish connection to Databricks"""
        try:
            print("Connecting to Databricks...")
            self.connection = sql.connect(
                server_hostname=self.server_hostname,
                http_path=self.http_path,
                access_token=self.access_token
            )
            self.cursor = self.connection.cursor()
            print("[SUCCESS] Successfully connected to Databricks")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to connect to Databricks: {str(e)}")
            return False
    
    def list_catalogs(self):
        """List all available catalogs"""
        try:
            query = "SHOW CATALOGS"
            print("\nListing available catalogs...")
            self.cursor.execute(query)
            results = self.cursor.fetchall()
            print("\nAvailable Catalogs:")
            print("-" * 40)
            for row in results:
                print(f"  - {row[0]}")
            return results
        except Exception as e:
            print(f"[ERROR] Failed to list catalogs: {str(e)}")
            return []
    
    def create_schema(self, schema_name):
        """
        Create a schema if it doesn't exist
        
        Args:
            schema_name (str): Name of the schema to create
        """
        try:
            query = f"CREATE SCHEMA IF NOT EXISTS {self.catalog}.{schema_name}"
            print(f"\nCreating schema '{schema_name}'...")
            self.cursor.execute(query)
            print(f"[SUCCESS] Schema '{schema_name}' is ready")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create schema: {str(e)}")
            return False
    
    def create_table(self, schema_name, table_name, columns):
        """
        Create a table if it doesn't exist
        
        Args:
            schema_name (str): Name of the schema
            table_name (str): Name of the table
            columns (str): Column definitions (e.g., "id INT, name STRING, created_at TIMESTAMP")
        """
        try:
            full_table_name = f"{self.catalog}.{schema_name}.{table_name}"
            query = f"""
            CREATE TABLE IF NOT EXISTS {full_table_name} (
                {columns}
            )
            """
            print(f"\nCreating table '{table_name}' in schema '{schema_name}'...")
            self.cursor.execute(query)
            print(f"[SUCCESS] Table '{full_table_name}' is ready")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create table: {str(e)}")
            return False
    
    def describe_table(self, schema_name, table_name):
        """
        Describe table structure
        
        Args:
            schema_name (str): Name of the schema
            table_name (str): Name of the table
        """
        try:
            full_table_name = f"{self.catalog}.{schema_name}.{table_name}"
            query = f"DESCRIBE TABLE {full_table_name}"
            print(f"\nTable structure for '{full_table_name}':")
            self.cursor.execute(query)
            
            results = self.cursor.fetchall()
            print("\n{:<20} {:<15} {:<30}".format("Column", "Type", "Comment"))
            print("-" * 65)
            for row in results:
                print("{:<20} {:<15} {:<30}".format(
                    row[0] or '', 
                    row[1] or '', 
                    row[2] or ''
                ))
            return True
        except Exception as e:
            print(f"[ERROR] Failed to describe table: {str(e)}")
            return False
    
    def insert_sample_data(self, schema_name, table_name):
        """
        Insert sample data into the table
        
        Args:
            schema_name (str): Name of the schema
            table_name (str): Name of the table
        """
        try:
            full_table_name = f"{self.catalog}.{schema_name}.{table_name}"
            query = f"""
            INSERT INTO {full_table_name} (id, name, created_at)
            VALUES 
                (1, 'Alice', current_timestamp()),
                (2, 'Bob', current_timestamp()),
                (3, 'Charlie', current_timestamp())
            """
            print(f"\nInserting sample data into '{full_table_name}'...")
            self.cursor.execute(query)
            print("[SUCCESS] Sample data inserted successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to insert data: {str(e)}")
            return False
    
    def query_table(self, schema_name, table_name, limit=10):
        """
        Query data from the table
        
        Args:
            schema_name (str): Name of the schema
            table_name (str): Name of the table
            limit (int): Number of rows to fetch
        """
        try:
            full_table_name = f"{self.catalog}.{schema_name}.{table_name}"
            query = f"SELECT * FROM {full_table_name} LIMIT {limit}"
            print(f"\nQuerying data from '{full_table_name}':")
            self.cursor.execute(query)
            
            results = self.cursor.fetchall()
            if results:
                print("\n{:<10} {:<20} {:<30}".format("ID", "Name", "Created At"))
                print("-" * 60)
                for row in results:
                    print("{:<10} {:<20} {:<30}".format(
                        str(row[0]), 
                        str(row[1]), 
                        str(row[2])
                    ))
            else:
                print("No data found in the table")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to query table: {str(e)}")
            return False
    
    def close(self):
        """Close the database connection"""
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
            print("\n[SUCCESS] Connection closed")


def main():
    """Main execution function"""
    print("=" * 70)
    print("Databricks Connection and Table Creation")
    print("=" * 70)
    
    # Initialize manager
    try:
        db_manager = DatabricksManager()
    except ValueError as e:
        print(f"\n[ERROR] Configuration Error: {str(e)}")
        sys.exit(1)
    
    # Connect to Databricks
    if not db_manager.connect():
        sys.exit(1)
    
    try:
        # First, list available catalogs
        catalogs = db_manager.list_catalogs()
        
        if not catalogs:
            print("\n[ERROR] No catalogs found or unable to list catalogs")
            sys.exit(1)
        
        # Define schema and table details
        schema_name = "my_schema"
        table_name = "paul"
        columns = "name STRING"
        
        # Create schema
        if not db_manager.create_schema(schema_name):
            sys.exit(1)
        
        # Create table
        if not db_manager.create_table(schema_name, table_name, columns):
            sys.exit(1)
        
        # Describe table structure
        db_manager.describe_table(schema_name, table_name)
        
        print("\n" + "=" * 70)
        print("[SUCCESS] All operations completed successfully!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n[ERROR] An error occurred: {str(e)}")
        sys.exit(1)
    finally:
        db_manager.close()


if __name__ == "__main__":
    main()

# Made with Bob
