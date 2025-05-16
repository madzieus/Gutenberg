import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
import urllib.request
import re
from collections import Counter
from urllib.parse import urlparse
from charset_normalizer import detect
import string
from pathlib import Path
from typing import List, Tuple

# Stop words to filter out common words
STOP_WORDS = {
    'the', 'and', 'to', 'of', 'a', 'in', 'is', 'it', 'for', 'on', 'with',
    'by', 'at', 'this', 'but', 'or', 'an', 'be', 'from', 'as', 'that', 'are',
    'was', 'were', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'must',
    'project', 'gutenberg', 'gutenberg™', 'ebook', 'edition', 'online', 'http', 'www',
    'i', 'you', 'he', 'she', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
    'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'ours', 'theirs',
    'these', 'those', 'which', 'what', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how',
    'am', 'is', 'are', 'was', 'were', 'been', 'being',
    'have', 'has', 'had', 'having',
    'do', 'does', 'did', 'doing',
    'if', 'than', 'then', 'so', 'because', 'although', 'though', 'while', 'before', 'after',
    'about', 'into', 'through', 'over', 'under', 'again', 'further', 'up', 'down', 'out',
    'very', 'more', 'most', 'some', 'any', 'each', 'few', 'many', 'such',
    'only', 'just', 'now', 'too', 'also', 'even', 'still', 'yet',
    'thou', 'thee', 'thy', 'thine', 'hath', 'doth', 'shalt', 'art',
    'said', 'say', 'says', 'shall', 'come', 'came', 'go', 'went', 'know', 'knew',
    'look', 'looked', 'see', 'saw', 'felt', 'thought', 'told', 'made', 'make', 'found', 'asked', 'replied',
}

def remove_html_tags(text: str) -> str:
    """
    Remove HTML tags from the input text using regular expressions.

    This function uses a regular expression to identify and remove all HTML tags
    (e.g., <p>, </div>) from the provided text, leaving only the plain text content.
    It is used to clean text fetched from Project Gutenberg URLs.

    Args:
        text (str): The input text containing potential HTML tags.

    Returns:
        str: The cleaned text with all HTML tags removed.

    Example:
        >>> remove_html_tags("<p>Hello</p> <b>World</b>")
        'Hello World'
    """
    clean_pattern = re.compile(r'<.*?>')
    return re.sub(clean_pattern, '', text)

class BookManager:
    """
    Manages database operations for storing and retrieving book data.

    This class handles interactions with a SQLite database to store book titles
    and their most frequent words with corresponding frequencies. It provides
    methods for initializing the database, saving, deleting, and fetching data.
    The database is stored in the user's home directory under '.booksearch/books.db'.
    """
    DB_DIR = Path.home() / ".booksearch"
    DB_PATH = DB_DIR / "books.db"
    TABLE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            word TEXT NOT NULL,
            frequency INTEGER NOT NULL
        )
    """
    TOP_WORDS_LIMIT = 10

    def __init__(self):
        """
        Initialize the SQLite database connection and create the books table.

        Creates the database directory if it does not exist and establishes a
        connection to the SQLite database. The books table is created with columns
        for id, title, word, and frequency if it does not already exist.

        Raises:
            RuntimeError: If database initialization fails due to SQLite errors.
        """
        try:
            self.DB_DIR.mkdir(exist_ok=True)
            self.conn = sqlite3.connect(self.DB_PATH)
            self.cursor = self.conn.cursor()
            self.cursor.execute(self.TABLE_SCHEMA)
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Database initialization failed: {e}")

    def __del__(self):
        """
        Close the database connection when the BookManager object is destroyed.

        Ensures that the SQLite database connection is properly closed to free
        system resources when the BookManager instance is garbage collected.
        Checks if the connection exists to avoid errors if initialization failed.
        """
        if hasattr(self, 'conn'):
            self.conn.close()

    def save_book_data(self, title: str, top_words: List[Tuple[str, int]]) -> None:
        """
        Save a book's title and its top words with their frequencies to the database.

        Inserts multiple records into the books table, each containing the book title,
        a word, and its frequency. The operation is performed as a single transaction
        to ensure data integrity.

        Args:
            title (str): The title of the book.
            top_words (List[Tuple[str, int]]): A list of tuples, each containing a word
                and its frequency.

        Raises:
            RuntimeError: If the database operation fails due to SQLite errors.
        """
        try:
            self.cursor.executemany(
                "INSERT INTO books (title, word, frequency) VALUES (?,?,?)",
                [(title, word, freq) for word, freq in top_words]
            )
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to save data to database: {e}")

    def delete_book_data(self, title: str) -> None:
        """
        Delete all records associated with a given book title from the database.

        Removes all entries in the books table where the title matches the provided
        title. The operation is committed to ensure the changes are saved.

        Args:
            title (str): The title of the book to delete.

        Raises:
            RuntimeError: If the database operation fails due to SQLite errors.
        """
        try:
            self.cursor.execute("DELETE FROM books WHERE title = ?", (title,))
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to delete book data: {e}")

    def delete_all_records(self) -> None:
        """
        Delete all records from the books table.

        Clears the entire books table, removing all stored book titles, words, and
        frequencies. The operation is committed to ensure the changes are saved.

        Raises:
            RuntimeError: If the database operation fails due to SQLite errors.
        """
        try:
            self.cursor.execute("DELETE FROM books")
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to delete all records: {e}")

    def fetch_book_data(self, title: str) -> List[Tuple[str, int]]:
        """
        Retrieve word frequencies for a given book title from the database.

        Queries the books table to fetch all words and their frequencies associated
        with the specified title. The search is case-insensitive, using LOWER() to
        compare titles.

        Args:
            title (str): The title of the book to fetch data for.

        Returns:
            List[Tuple[str, int]]: A list of tuples, each containing a word and its
                frequency for the specified title.

        Raises:
            RuntimeError: If the database operation fails due to SQLite errors.
        """
        try:
            self.cursor.execute(
                "SELECT word, frequency FROM books WHERE LOWER(title) = LOWER(?)",
                (title,)
            )
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to fetch book data: {e}")

    def fetch_all_titles(self) -> List[str]:
        """
        Fetch all unique book titles from the database, sorted by most recent.

        Queries the books table to retrieve all distinct titles, ordered by their
        id in descending order (most recent first). This is used to populate the
        history listbox in the GUI.

        Returns:
            List[str]: A list of unique book titles.

        Raises:
            RuntimeError: If the database operation fails due to SQLite errors.
        """
        try:
            self.cursor.execute("SELECT DISTINCT title FROM books ORDER BY id DESC")
            return [row[0] for row in self.cursor.fetchall()]
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to fetch titles: {e}")

class BookSearchApp:
    """
    A Tkinter-based GUI application for searching and storing ebook data from Project Gutenberg.

    This class implements the user interface and logic for fetching, analyzing, and
    storing book data. It interacts with the BookManager class to manage database operations
    and displays results in a Tkinter window. The application allows users to search books
    by title or URL, view frequent words, and manage stored books.
    """
    TOP_WORDS_LIMIT = 10

    def __init__(self, root: tk.Tk):
        """
        Initialize the BookSearchApp with a Tkinter root window.

        Sets up the main application window, configures its title and background,
        initializes the BookManager instance for database operations, and creates
        a translation table for text cleaning. Finally, it calls create_widgets to
        set up the GUI components.

        Args:
            root (tk.Tk): The Tkinter root window for the application.
        """
        self.root = root
        self.root.title("Project Gutenberg Book Search")
        self.root.configure(bg="#f0f0f0")  # Light gray background
        self.book_manager = BookManager()
        self.translator = str.maketrans('', '', string.punctuation)
        self.create_widgets()

    def create_widgets(self) -> None:
        """
        Create and configure all Tkinter widgets for the application GUI.

        Sets up the layout of the application, including labels, entry fields, buttons,
        a text area for results, and a listbox for history. Configures styles for labels
        and buttons, and binds events to handle user interactions. The widgets are arranged
        using the grid geometry manager.
        """
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#f0f0f0", foreground="#333333", font=("Courier New", 10))
        style.configure("TButton", background="#4a90e2", foreground="#ffffff", font=("Courier New", 10, "bold"))
        style.map("TButton", background=[("active", "#357abd")])

        self.root.grid_columnconfigure(1, weight=1, uniform="group1")

        self.intro_label = ttk.Label(
            self.root,
            text=(
                "Usage Info:\n"
                "1. If you only specify a Book Title (no URL), the application will search it in the local database.\n"
                "2. If you want to add a new book from Project Gutenberg, provide both a Book Title and a valid URL.\n"
                "3. If a record with the same Book Title exists, delete it first to create a new one."
            ),
            wraplength=500
        )
        self.intro_label.grid(row=0, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        self.title_label = ttk.Label(self.root, text="Book Title:")
        self.title_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")

        self.title_entry = tk.Entry(
            self.root,
            width=50,
            bg="white",
            fg="black",
            insertbackground="black",
            insertwidth=2,
            highlightthickness=1,
            highlightcolor="#cccccc",
            highlightbackground="#cccccc",
            font=("Courier New", 10)
        )
        self.title_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.search_title_button = ttk.Button(self.root, text="Search By Title", command=self.search_by_title)
        self.search_title_button.grid(row=1, column=2, padx=5, pady=5)

        self.url_label = ttk.Label(self.root, text="Project Gutenberg URL:")
        self.url_label.grid(row=2, column=0, padx=5, pady=5, sticky="e")

        self.url_entry = tk.Entry(
            self.root,
            width=50,
            bg="white",
            fg="black",
            insertbackground="black",
            insertwidth=2,
            highlightthickness=1,
            highlightcolor="#cccccc",
            highlightbackground="#cccccc",
            font=("Courier New", 10)
        )
        self.url_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.search_url_button = ttk.Button(self.root, text="Search By URL", command=self.search_by_url)
        self.search_url_button.grid(row=2, column=2, padx=5, pady=5)

        self.output_label = ttk.Label(self.root, text="Top Words:")
        self.output_label.grid(row=3, column=0, padx=5, pady=5, sticky="ne")

        self.output_text = tk.Text(
            self.root,
            width=50,
            height=15,
            bg="white",
            fg="black",
            font=("Courier New", 10),
            insertbackground="black",
            insertwidth=2,
            highlightthickness=0,
            highlightcolor="#ffffff",
            highlightbackground="#ffffff",
            state=tk.DISABLED,
            cursor="arrow",
            takefocus=0
        )
        self.output_text.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        self.clear_button = ttk.Button(self.root, text="Clear", command=self.clear_fields)
        self.clear_button.grid(row=4, column=1, padx=5, pady=5)

        self.history_label = ttk.Label(self.root, text="Local Database:")
        self.history_label.grid(row=5, column=0, padx=5, pady=5, sticky="e")

        self.history_frame = tk.Frame(self.root)
        self.history_frame.grid(row=5, column=1, padx=5, pady=5, sticky="nsew")

        self.history_scrollbar = tk.Scrollbar(self.history_frame, orient="vertical")
        self.history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_listbox = tk.Listbox(
            self.history_frame,
            width=50,
            height=10,
            bg="white",
            fg="black",
            font=("Courier New", 10),
            highlightthickness=1,
            highlightcolor="#cccccc",
            highlightbackground="#cccccc",
            yscrollcommand=self.history_scrollbar.set
        )
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.history_scrollbar.config(command=self.history_listbox.yview)

        self.history_listbox.bind("<<ListboxSelect>>", self.load_history_selection)

        self.delete_history_button = ttk.Button(self.root, text="Delete", command=self.delete_selected_search)
        self.delete_history_button.grid(row=5, column=2, padx=5, pady=5)

        self.delete_all_button = ttk.Button(self.root, text="Delete All Records", command=self.delete_all_records)
        self.delete_all_button.grid(row=6, column=2, padx=5, pady=5)

        self.populate_history()

    def clear_fields(self) -> None:
        """
        Clear all input fields and the output text area in the GUI.

        Resets the title and URL entry fields to empty and clears the output text
        area used to display word frequencies. The output text area is temporarily
        set to NORMAL state to allow clearing, then reverted to DISABLED to prevent
        user editing.
        """
        self.title_entry.delete(0, tk.END)
        self.url_entry.delete(0, tk.END)
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.config(state=tk.DISABLED)

    def sanitize_input(self, text: str, max_length: int = 255) -> str:
        """
        Sanitize user input by removing special characters and limiting length.

        Removes all characters except alphanumeric, whitespace, and hyphens from
        the input text, strips leading/trailing whitespace, and truncates the result
        to the specified maximum length. Used to clean book titles before database
        operations.

        Args:
            text (str): The input text to sanitize.
            max_length (int, optional): Maximum length of the sanitized text. Defaults to 255.

        Returns:
            str: The sanitized text.
        """
        sanitized = re.sub(r'[^\w\s-]', '', text.strip())[:max_length]
        return sanitized

    def is_valid_gutenberg_url(self, url: str) -> bool:
        """
        Validate if a URL is a well-formed Project Gutenberg URL.

        Checks if the URL uses HTTP or HTTPS and has a domain containing 'gutenberg.org'.
        Used to ensure that only valid Project Gutenberg URLs are processed for fetching
        book text.

        Args:
            url (str): The URL to validate.

        Returns:
            bool: True if the URL is valid, False otherwise.
        """
        try:
            parsed = urlparse(url)
            return parsed.scheme in ('http', 'https') and 'gutenberg.org' in parsed.netloc
        except ValueError:
            return False

    def search_by_title(self) -> None:
        """
        Search the local database for a book by title and display its top words.

        Retrieves the title from the title entry field, queries the database for
        word frequencies associated with that title, and displays the top 10 words
        in the output text area. If the title is not found, a message is displayed
        prompting the user to provide a URL. The search is case-insensitive.

        Raises:
            RuntimeError: If the database query fails, an error message is shown in a dialog.
        """
        title = self.title_entry.get()
        if not title.strip():
            messagebox.showwarning("Warning", "Please enter a book title (no empty field allowed).")
            return

        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.config(state=tk.DISABLED)

        try:
            results = self.book_manager.fetch_book_data(title)
            if results:
                results_sorted = sorted(results, key=lambda x: x[1], reverse=True)[:self.TOP_WORDS_LIMIT]
                self.display_top_words(results_sorted)
            else:
                self.output_text.config(state=tk.NORMAL)
                self.output_text.insert(tk.END, "Book not found in local database.\n\n")
                self.output_text.insert(
                    tk.END,
                    "If you have a valid Project Gutenberg URL for this book, provide both Title and URL, then click 'Search By URL'."
                )
                self.output_text.config(state=tk.DISABLED)
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))

    def search_by_url(self) -> None:
        """
        Fetch a book from a Project Gutenberg URL, analyze it, and store its top words.

        Retrieves the title and URL from the GUI, validates the URL, fetches the book
        text, analyzes it to find the top 10 words (excluding stop words), and saves
        the results to the database. The top words are displayed in the output text area.
        If the title already exists in the database, the user is prompted to delete it first.
        The search URL button is disabled during processing to prevent multiple submissions.

        Raises:
            RuntimeError: If fetching or saving fails, an error message is shown in a dialog.
        """
        title = self.sanitize_input(self.title_entry.get())
        url = self.url_entry.get().strip()

        if not title:
            messagebox.showwarning("Warning", "You must provide a non-empty book title before adding a new book.")
            return

        existing_data = self.book_manager.fetch_book_data(title)
        if existing_data:
            messagebox.showinfo(
                "Title Exists",
                "A record with this title already exists in the local database.\n"
                "Please delete that record first if you want to create a new entry with the same title."
            )
            return

        if not url or not self.is_valid_gutenberg_url(url):
            messagebox.showwarning("Warning", "Please enter a valid Project Gutenberg URL.")
            return

        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, "Loading...\n")
        self.output_text.config(state=tk.DISABLED)

        self.search_url_button.config(state="disabled")
        self.root.update()

        try:
            self.book_manager.delete_book_data(title)
            text_content = self.fetch_text_from_url(url)
            top_words = self.get_top_ten_words(text_content)
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete("1.0", tk.END)

            if not top_words:
                self.output_text.insert(tk.END, "Book was not found or text is empty.")
                self.output_text.config(state=tk.DISABLED)
                return

            self.book_manager.save_book_data(title, top_words)
            self.output_text.config(state=tk.DISABLED)
            self.display_top_words(top_words)
            self.populate_history()

        except RuntimeError as e:
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete("1.0", tk.END)
            messagebox.showerror("Error", str(e))
            self.output_text.config(state=tk.DISABLED)
        finally:
            self.search_url_button.config(state="normal")

    def fetch_text_from_url(self, url: str) -> str:
        """
        Fetch text from a Project Gutenberg URL and remove HTML tags.

        Downloads the content from the specified URL, detects its character encoding,
        decodes the content to a string, and removes HTML tags. The function handles
        network and HTTP errors gracefully.

        Args:
            url (str): The URL of the Project Gutenberg ebook to fetch.

        Returns:
            str: The cleaned text content of the ebook.

        Raises:
            RuntimeError: If the HTTP request fails, a network error occurs, or an
                unexpected error is encountered.
        """
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
                detected = detect(data)
                charset = detected['encoding'] or 'utf-8'
                text = data.decode(charset, errors='replace')
            return remove_html_tags(text)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP Error: {e.code} - {e.reason}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network Error: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error: {e}")

    def get_top_ten_words(self, text: str) -> List[Tuple[str, int]]:
        """
        Analyze text to find the top 10 most frequent words, excluding stop words.

        Cleans the input text by removing punctuation and converting to lowercase,
        splits it into words, filters out stop words, and counts the frequency of
        remaining words. Returns the top 10 words with their frequencies, sorted
        by frequency in descending order.

        Args:
            text (str): The text to analyze.

        Returns:
            List[Tuple[str, int]]: A list of tuples, each containing a word and its
                frequency, up to a maximum of 10.
        """
        cleaned_text = text.translate(self.translator).lower()
        words = [word for word in cleaned_text.split() if word not in STOP_WORDS]
        if not words:
            return []
        counter = Counter(words)
        return counter.most_common(self.TOP_WORDS_LIMIT)

    def display_top_words(self, top_words: List[Tuple[str, int]]) -> None:
        """
        Display the top words and their frequencies in the output text area.

        Formats the provided list of word-frequency pairs into a table with aligned
        columns and displays it in the GUI's output text area. If the list is empty,
        a "No words found" message is shown. The text area is set to NORMAL state for
        writing and then reverted to DISABLED.

        Args:
            top_words (List[Tuple[str, int]]): A list of tuples, each containing a word
                and its frequency.
        """
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)

        if not top_words:
            self.output_text.insert(tk.END, "No words found.")
            self.output_text.config(state=tk.DISABLED)
            return

        header = f"{'Word':<30}{'Frequency':>10}\n"
        separator = "-" * 40 + "\n"
        self.output_text.insert(tk.END, header)
        self.output_text.insert(tk.END, separator)

        for word, freq in top_words:
            line = f"{word:<30}{freq:>10}\n"
            self.output_text.insert(tk.END, line)

        self.output_text.config(state=tk.DISABLED)

    def populate_history(self) -> None:
        """
        Populate the history listbox with all book titles from the database.

        Clears the current contents of the history listbox and fills it with all
        unique book titles retrieved from the database, sorted by most recent. If
        an error occurs, an error message is displayed in a dialog.

        Raises:
            RuntimeError: If fetching titles fails, an error message is shown.
        """
        self.history_listbox.delete(0, tk.END)
        try:
            for title in self.book_manager.fetch_all_titles():
                self.history_listbox.insert(tk.END, title)
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))

    def load_history_selection(self, event: tk.Event) -> None:
        """
        Load the selected title from the history listbox and perform a search.

        When a title is selected in the history listbox, this method retrieves the
        title, inserts it into the title entry field, and triggers a search by title
        to display its word frequencies.

        Args:
            event (tk.Event): The Tkinter event triggered by selecting an item in the listbox.
        """
        selection = self.history_listbox.curselection()
        if selection:
            title = self.history_listbox.get(selection[0])
            self.title_entry.delete(0, tk.END)
            self.title_entry.insert(0, title)
            self.search_by_title()

    def delete_selected_search(self) -> None:
        """
        Delete the selected book title from the database and refresh the history listbox.

        Retrieves the selected title from the history listbox, removes all associated
        records from the database, and updates the listbox to reflect the current state
        of the database. If no title is selected, a warning is shown.

        Raises:
            RuntimeError: If the database operation fails, an error message is shown.
        """
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select an item from the list to delete.")
            return

        title = self.history_listbox.get(selection[0])
        try:
            self.book_manager.delete_book_data(title)
            self.populate_history()
        except RuntimeError as e:
            messagebox.showerror("Error", str(e))

    def delete_all_records(self) -> None:
        """
        Delete all records from the database after user confirmation.

        Prompts the user to confirm deletion of all records in the database. If confirmed,
        clears the books table and refreshes the history listbox. If an error occurs,
        an error message is displayed.

        Raises:
            RuntimeError: If the database operation fails, an error message is shown.
        """
        if messagebox.askyesno("Confirm", "Are you sure you want to delete all records? This cannot be undone."):
            try:
                self.book_manager.delete_all_records()
                self.populate_history()
            except RuntimeError as e:
                messagebox.showerror("Error", str(e))

def main():
    """
    Main entry point for the Project Gutenberg Book Search application.

    Creates the Tkinter root window, initializes the BookSearchApp, and starts
    the Tkinter event loop to handle user interactions. This function is called
    when the script is run directly.
    """
    root = tk.Tk()
    app = BookSearchApp(root)
    root.mainloop()

if __name__ == "__main__":
    """
    Execute the main function when the script is run directly.

    This conditional ensures that the main function is only called if the script
    is executed as the main module, not when it is imported as a module.
    """
    main()