import csv
from chat_window import ChatApp
from colorama import Fore
import tkinter as tk

from chatalogue import chat_loop


def check_user_answer(csv_file_path):
    """
    Reads a CSV file with 'query' and 'answer' columns.
    sends the query to the chatalogue,
    checks if the answer form the csv file is in the response from the chatalogue
    """
    g=0
    with open(csv_file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:

            query = row.get("query", "").strip().lower()
            correct_answer = row.get("answer", "").strip().lower()

            generated_answer = call_chat(query).lower()

            if correct_answer in generated_answer:
                print(Fore.GREEN + f"{query} : Passed")

            else:
                print(Fore.RED + f"{query} : Failed")
                print(f"trying {query} 3 more times")
                for i in range(3):
                    generated_answer = call_chat(query).lower()
                    if correct_answer in generated_answer:
                        print(Fore.GREEN + f"{query} : Passed")
                        break

                    if i == 2:
                        print(Fore.RED + f"{query} : Failed 3 more times call Preetham")


            if g == 28:
                return
            g += 1



def call_chat(input):
    """
    sends the input to the chat_bot
    returns the response
    """
    response = chat_loop(input)
    return response

# ------- Example Usage -------

def main():

    csv_path = "test_bot_results.csv"
    check_user_answer(csv_path)


if __name__ == "__main__":
    main()