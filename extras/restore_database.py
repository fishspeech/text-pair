"""Restores TextPAIR database and web files from a backup tarball, and rebuilds the web application."""

import json
import os
import shutil
import subprocess
from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path

import lz4.frame
import psycopg2

GLOBAL_CONFIG = ConfigParser()
GLOBAL_CONFIG.read("/etc/text-pair/global_settings.ini")


def check_database_connection(user, password):
    """Test database connection and permissions."""
    try:
        conn = psycopg2.connect(
            database=GLOBAL_CONFIG.get("DATABASE", "database_name"),
            user=user,
            password=password
        )
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print(f"Database connection error: {e}")
        return False


def update_app_config(web_app_path):
    """
    Update the appConfig.json file with the API server from global settings
    and update PhiloLogic paths to point to the backed up data.
    Returns True if successful, False otherwise.
    """
    try:
        config_path = web_app_path / "appConfig.json"
        if not config_path.exists():
            print(f"Warning: appConfig.json not found at {config_path}")
            return False

        # Read the current config
        with open(config_path) as f:
            config = json.load(f)

        # Update the apiServer value
        api_server = GLOBAL_CONFIG.get("WEB_APP", "api_server")
        config['apiServer'] = api_server

        # Update PhiloLogic paths to point to the restored data
        source_data_path = web_app_path / "source_data"
        if source_data_path.exists():
            config['sourcePhiloDBPath'] = str(source_data_path.absolute())

        target_data_path = web_app_path / "target_data"
        if target_data_path.exists():
            config['targetPhiloDBPath'] = str(target_data_path.absolute())
        elif 'targetPhiloDBPath' in config:
            # If target_data doesn't exist and there was a target path, remove it
            config['targetPhiloDBPath'] = ""

        # Write the updated config back
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        print(f"Updated appConfig.json:")
        print(f"  - apiServer: {api_server}")
        print(f"  - sourcePhiloDBPath: {config['sourcePhiloDBPath']}")
        if config.get('targetPhiloDBPath'):
            print(f"  - targetPhiloDBPath: {config['targetPhiloDBPath']}")

        return True

    except Exception as e:
        print(f"Error updating appConfig.json: {e}")
        return False


def run_npm_build(web_app_path):
    """
    Run npm install and build in the web app directory.
    Returns True if successful, False otherwise.
    """
    try:
        # Change to web app directory
        original_dir = os.getcwd()
        os.chdir(web_app_path)

        # Run npm install
        print("Running npm install...")
        subprocess.run(['npm', 'install'], check=True)

        # Run npm build
        print("Running npm run build...")
        subprocess.run(['npm', 'run', 'build'], check=True)

        return True

    except subprocess.CalledProcessError as e:
        print(f"Error during npm build process: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error during build process: {e}")
        return False
    finally:
        # Always return to original directory
        os.chdir(original_dir)


def check_existing_resources(db_name, db_user, db_password, web_app_dest, backup_dir):
    """Check for existing database tables and web app directory."""
    existing_resources = []

    # Check for existing tables
    sql_files = list(backup_dir.glob("textpair_*.sql"))
    for sql_file in sql_files:
        table_name = sql_file.stem.replace('textpair_', '')
        with psycopg2.connect(database=db_name, user=db_user, password=db_password) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table_name,)
                )
                if cursor.fetchone() is not None:
                    existing_resources.append(f"database table '{table_name}'")

    # Check for existing web app directory
    web_dirs = [d for d in backup_dir.iterdir() if d.is_dir()]
    if web_dirs and (web_app_dest / web_dirs[0].name).exists():
        existing_resources.append(f"web application directory '{web_dirs[0].name}'")

    return existing_resources


def restore_textpair_database(backup_path, web_app_dest=None, force=False):
    """
    Restore TextPAIR database and web files from a backup tarball.

    Args:
        backup_path: Path to the backup tarball
        web_app_dest: Optional destination for web app files. If not provided,
                     uses the path from global_settings.ini
        force: If True, overwrite existing files/tables without prompting
    """
    print(f"\nStarting TextPAIR restoration from: {backup_path}")

    db_name = GLOBAL_CONFIG.get("DATABASE", "database_name")
    db_user = GLOBAL_CONFIG.get("DATABASE", "database_user")
    db_password = GLOBAL_CONFIG.get("DATABASE", "database_password")

    # Check database connection before proceeding
    print("\nChecking database connection...")
    if not check_database_connection(db_user, db_password):
        raise Exception("Cannot connect to database. Please check credentials and permissions.")
    print("✓ Database connection verified")

    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Create temporary directory for extraction
    print("\nPreparing temporary workspace...")
    temp_dir = Path("/tmp/textpair_restore_temp")
    if temp_dir.exists():
        print("  - Cleaning up existing temporary files...")
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    print("✓ Workspace prepared")

    restored_web_app_path = None

    try:
        # Extract the tarball using lz4 module
        print("\nExtracting backup archive...")
        print("  - Decompressing with LZ4...")
        with open(backup_path, 'rb') as f:
            compressed_data = f.read()
        decompressed_data = lz4.frame.decompress(compressed_data)
        print("  - Extracting files...")
        temp_tar = temp_dir / "temp.tar"
        with open(temp_tar, 'wb') as f:
            f.write(decompressed_data)
        os.system(f"tar xf {temp_tar} -C {temp_dir}")
        os.remove(temp_tar)
        print("✓ Backup extracted successfully")

        backup_contents = list(temp_dir.iterdir())
        if not backup_contents:
            raise Exception("Backup archive appears to be empty")

        backup_dir = backup_contents[0]
        if not backup_dir.is_dir():
            raise Exception("Unexpected backup structure")

        # Set up web app destination path
        if not web_app_dest:
            web_app_dest = Path(GLOBAL_CONFIG.get("WEB_APP", "web_app_path"))
        else:
            web_app_dest = Path(web_app_dest)

        # Check for existing resources
        if not force:
            print("\nChecking for existing resources...")
            existing = check_existing_resources(db_name, db_user, db_password, web_app_dest, backup_dir)
            if existing:
                print("\nWARNING: The following resources will be overwritten:")
                for resource in existing:
                    print(f"  - {resource}")
                response = input("\nDo you want to proceed with the restoration? This will replace all existing resources (y/n): ")
                if response.lower() != 'y':
                    print("Restoration cancelled")
                    return
                print("")  # Empty line for better readability

        # Restore database tables
        sql_files = list(backup_dir.glob("textpair_*.sql"))
        if not sql_files:
            raise Exception("No SQL files found in backup")

        print("\nRestoring database tables...")
        print(f"Found {len(sql_files)} tables to restore")

        for sql_file in sql_files:
            table_name = sql_file.stem.replace('textpair_', '')

            # Drop existing table if it exists
            print(f"  - Processing {table_name}:")
            print(f"    • Dropping existing table if present...")
            with psycopg2.connect(database=db_name, user=db_user, password=db_password) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                conn.commit()

            # Restore table
            print(f"    • Restoring table data...")
            os.system(f'PGPASSWORD={db_password} psql -U {db_user} -d {db_name} -f {sql_file}')
            print(f"    ✓ Table {table_name} restored")

        print("✓ Database restoration complete")

        # Restore web app files
        web_dirs = [d for d in backup_dir.iterdir() if d.is_dir()]
        if web_dirs:
            web_app_dir = web_dirs[0]
            web_app_dest = web_app_dest / web_app_dir.name

            if web_app_dest.exists():
                print(f"\nRemoving existing web application at {web_app_dest}...")
                shutil.rmtree(web_app_dest)

            print(f"Copying web application files...")
            shutil.copytree(web_app_dir, web_app_dest)
            restored_web_app_path = web_app_dest
            print("✓ Web application files restored")

        # Update app configuration and rebuild web application if it was restored
        if restored_web_app_path:
            print("\nConfiguring web application...")
            if not update_app_config(restored_web_app_path):
                print("Failed to update web application configuration")
                if not force:
                    raise Exception("Web application configuration update failed")
            print("✓ Configuration updated")

            print("\nRebuilding web application...")
            print("  - Installing dependencies...")
            if run_npm_build(restored_web_app_path):
                print("✓ Web application rebuilt successfully")
            else:
                print("✗ Failed to rebuild web application")
                if not force:
                    raise Exception("Web application build failed")

        print("\n✓ Restore completed successfully!")
        db_url = Path(GLOBAL_CONFIG.get("WEB_APP", "api_server").replace("-api", "")) / web_app_dest.name
        print(f"The database is viewable at: {db_url}")

    finally:
        # Clean up
        print("\nCleaning up...")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        os.remove(backup_path)
        print("✓ Cleanup completed")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("backup_path", type=str, help="Path to the backup tarball file")
    parser.add_argument("--web_app_dest", type=str, default="",
                      help="Optional destination path for web app files")
    parser.add_argument("--force", action="store_true",
                      help="Overwrite existing files/tables without prompting")
    args = parser.parse_args()

    restore_textpair_database(args.backup_path, args.web_app_dest, args.force)