import os
from datetime import datetime
from pathlib import Path

from promg import SemanticHeader, Performance, OcedPg
from promg import DatabaseConnection
from promg import authentication
from promg import DatasetDescriptions

# several steps of import, each can be switch on/off
from colorama import Fore
from promg.modules.db_management import DBManagement

connection = authentication.connections_map[authentication.Connections.LOCAL]

dataset_name = 'library'
use_sample = False
use_preprocessed_files = False  # if false, read/import files instead
batch_size = 100000

semantic_header_path = Path(f'json_files/{dataset_name}.json')
semantic_header = SemanticHeader.create_semantic_header(semantic_header_path)

perf_path = os.path.join("..", "perf", dataset_name, f"{dataset_name}Performance.csv")

ds_path = Path(f'json_files/{dataset_name}_DS.json')
datastructures = DatasetDescriptions(ds_path)

step_clear_db = True
step_populate_graph = True

connection_key = authentication.Connections.LOCAL
verbose = False


def main() -> None:
    """
    Main function, read all the logs, clear and create the graph, perform checks
    @return: None
    """
    print("Started at =", datetime.now().strftime("%H:%M:%S"))
    if use_preprocessed_files:
        print(Fore.RED + '💾 Preloaded files are used!' + Fore.RESET)
    else:
        print(Fore.RED + '📝 Importing and creating files' + Fore.RESET)

    performance = Performance.set_up_performance(dataset_name=dataset_name, use_sample=use_sample)
    db_connection = DatabaseConnection.set_up_connection_using_key(key=connection_key,
                                                                   verbose=verbose,
                                                                   batch_size=batch_size)

    db_manager = DBManagement()
    if step_clear_db:
        db_manager.clear_db(replace=True)
        db_manager.set_constraints()

    if step_populate_graph:
        oced_pg = OcedPg(dataset_descriptions=datastructures,
                         use_sample=use_sample,
                         use_preprocessed_files=use_preprocessed_files,
                         semantic_header=semantic_header)
        oced_pg.run()

    performance.finish_and_save()
    db_manager.print_statistics()

    db_connection.close_connection()


if __name__ == "__main__":
    main()
