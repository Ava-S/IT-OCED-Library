import random
from datetime import date
from pathlib import Path

import pandas as pd
from faker import Faker
from pandas import DataFrame

from library_simulation import Simulation

###### SETTINGS

NUM_YEARS = 1
WITH_VIOLATIONS = True

###### DETERMINE VALUES
fake = Faker()
Faker.seed(0)
random.seed(1)

NUM_YEARS = max(1, NUM_YEARS)  # ensure to simulate at least one year
END_YEAR = 2025 + NUM_YEARS
DAYS = 24 * 60
SIMULATION_DAYS = NUM_YEARS * 365


def calculate_category(born):
    today = date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    passed_age = sorted([key for key in age_categories.keys() if age - key >= 0], reverse=True)
    return age_categories[passed_age[0]]


def create_catalogue(books: DataFrame, library: int, sample_size: int):
    books_lib = books.sample(n=sample_size, random_state=library)
    books_lib['uID'] = '0' + str(library) + books_lib['bookID'].astype(str)
    books_lib.drop(columns=['bookID'], inplace=True)
    books_lib['library_id'] = f'library_{library}'
    # strip num pages column nape
    num_pages_column = [item for item in list(books_lib.columns) if "num_pages" in item][0]
    books_lib = books_lib.rename(columns={'uID': 'book_id', num_pages_column: num_pages_column.strip()})
    books_lib.to_csv(Path(f'1_output_data/library_{library}_books.csv'), index=False)
    return books_lib


# Dataset 1: Records of Books https://www.kaggle.com/datasets/jealousleopard/goodreadsbooks
books = pd.read_csv(Path(f'0_input_data/books.csv'))
# only keep books with sufficient reviews
books = books[books['text_reviews_count'] > 10]
books_lib1 = create_catalogue(books, library=1, sample_size=7000)

print("Created book dataset")

# Dataset 2: Records of Patrons
members = []
age_categories = {0: "Kid", 12: "Teen", 18: "Adolescent", 25: "Adult", 67: "Senior"}
subscription_types = ["Budget", "Comfort", "Deluxe"]

for i in range(1, 1200):
    date_of_birth = fake.date_of_birth(minimum_age=5, maximum_age=90)
    age_category = calculate_category(date_of_birth)

    member_record = {
        "member_id": f"M{i:03}",
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        "date_of_birth": date_of_birth,
        "age_category": age_category,
        "subscription_type": random.choice(subscription_types),
        "registration_id": 1 if random.random() < 0.75 else 2
    }

    members.append(member_record)

members_df = pd.DataFrame.from_records(members)
members_df.to_csv(Path(f'1_output_data/members.csv'), index=False)

members_df_lib1 = members_df.sample(n=1000, random_state=1)
members_df_lib2 = members_df.sample(n=400, random_state=2)

print("Created member dataset")

# bookIds = books['uID'].to_list()
# memberIds = members_df['member_id'].to_list()

number_of_libraries = 1
libraries = {
    "library_1": {
        "books": books_lib1['book_id'].to_list(),
        "members": members_df_lib1[['member_id', 'registration_id', 'subscription_type']].to_dict('records')
    }
}

simulation = Simulation(library_data=libraries, simulation_days=SIMULATION_DAYS)
simulation.run(end_year=END_YEAR + NUM_YEARS, with_violations=True)

print("Created event dataset")
