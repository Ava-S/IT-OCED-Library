from promg.modules.db_management import DBManagement
from promg import Configuration, DatabaseConnection, Performance, SemanticHeader, DatasetDescriptions, OcedPg, Query
import yaml


def get_graph_statistics(_db_connection):
    """
    Statistics about nodes and relations.
    """

    with _db_connection.driver.get_session(database=_db_connection.db_name) as session:
        print("\n=== GRAPH STATISTICS ===")

        try:
            node_query = """
            MATCH (n)
            WITH n, labels(n) as labels
            RETURN reduce(label_str = "(", l in labels | label_str + ":" + l) + ")" as label, count(n) as count ORDER 
            BY count DESC
            """
            node_counts = session.run(node_query)
            print("\n--- Node counts ---")
            for record in node_counts:
                print(f"{record['label']:<30} {record['count']}")

            rel_query = """
            MATCH (n) - [r] -> (n2)
            RETURN "[:" + type(r) + "]" as  type, count(r) as count ORDER BY count DESC
            """
            rel_counts = session.run(rel_query)
            print("\n--- Relationship counts ---")
            for record in rel_counts:
                print(f"{record['type']:<30} {record['count']}")

            total_nodes = session.run("MATCH (n) RETURN count(n) AS total").single()["total"]
            total_rels = session.run("MATCH ()-[r]->() RETURN count(r) AS total").single()["total"]

            print("\n--- Totals ---")
            print(f"Total nodes: {total_nodes}")
            print(f"Total relationships: {total_rels}")

        except Exception as e:
            print(f"Failed to get graph statistics: {e}")


def get_db_connection(config):
    # retrieve configuration for case_study
    db_connection = DatabaseConnection.set_up_connection(config=config)
    return db_connection

def get_config(conf_path):
    config = yaml.safe_load(open(conf_path))

    print(f"These are the credentials that I expect to be set for the database.")
    print(f"db_name: {config['db_name']}")
    print(f"uri: {config['uri']}")
    print(f"password: {config['password']}")
    print("----------------------")
    print(f"If you have other credentials, please change them at: {conf_path}")
    config = Configuration.init_conf_with_config_file(conf_path)
    return config



def clear_database(db_connection):
    db_manager = DBManagement(db_connection=db_connection, semantic_header=None)
    db_manager.clear_db()


def load_data(db_connection, conf_path):
    config = Configuration.init_conf_with_config_file(conf_path)
    dataset_descriptions = DatasetDescriptions(config=config)
    semantic_header = SemanticHeader.create_semantic_header(config=config)
    data_loader = OcedPg(database_connection=db_connection,
                         dataset_descriptions=dataset_descriptions,
                         semantic_header=semantic_header)
    data_loader.load()

def transform_data(db_connection, conf_path):
    config = Configuration.init_conf_with_config_file(conf_path)
    dataset_descriptions = DatasetDescriptions(config=config)
    semantic_header = SemanticHeader.create_semantic_header(config=config)
    data_loader = OcedPg(database_connection=db_connection,
                         dataset_descriptions=dataset_descriptions,
                         semantic_header=semantic_header)
    data_loader.transform()
