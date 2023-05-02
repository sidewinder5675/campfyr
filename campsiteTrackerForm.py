from flask import Flask, render_template, request, jsonify
import json
import logging
from urllib.parse import urlparse

from recreation_client import RecreationClient

app = Flask(__name__)
app = Flask(__name__, static_url_path="/static")

# json_location = '/app/camp/campSiteRequests.json'
json_location = "campSiteRequests.json"

data = []


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/get_data", methods=["GET"])
def get_data():
    load_data_from_file()  # Reload data from file
    return jsonify(data)


@app.route("/add_entry", methods=["POST"])
def add_entry():
    entry = request.get_json()
    campground_url = entry["campground_url"]
    campground_id = extract_campground_id(campground_url)
    campground_name = get_park_name(campground_id)
    entry["campground_id"] = campground_id
    entry["campground_name"] = campground_name
    data.append(entry)
    save_data_to_file()
    return jsonify({"message": "Entry added successfully"})


@app.route("/edit_entry", methods=["POST"])
def edit_entry():
    index = int(request.form["index"])
    entry = request.get_json()
    campground_url = entry["campground_url"]
    campground_id = extract_campground_id(campground_url)
    campground_name = get_park_name(campground_id)
    entry["campground_id"] = campground_id
    entry["campground_name"] = campground_name
    data[index] = entry
    save_data_to_file()
    return jsonify({"message": "Entry updated successfully"})


@app.route("/save_data", methods=["POST"])
def save_data():
    entries = request.get_json()
    data.clear()
    for entry in entries:
        campground_url = entry["campground_url"]
        campground_id = extract_campground_id(campground_url)
        campground_name = get_park_name(campground_id)
        entry["campground_id"] = campground_id
        entry["campground_name"] = campground_name
        data.append(entry)
    save_data_to_file()
    return jsonify({"message": "Data saved successfully"})


@app.route("/remove_entry", methods=["POST"])
def remove_entry():
    entry = request.get_json()
    entry_id = entry.get("id")  # Get the entry ID from the JSON payload

    if entry_id:
        # Find the index of the entry with the matching ID
        index = next((index for index, e in enumerate(data) if e["id"] == entry_id), -1)

        if index != -1:
            data.pop(index)
            save_data_to_file()
            return jsonify({"message": "Entry removed successfully"})
        else:
            return jsonify({"error": "Entry not found"})
    else:
        return jsonify({"error": "Invalid entry ID"})


def load_data_from_file():
    global data
    try:
        with open(json_location, "r") as file:
            data = json.load(file)
        print("Data loaded:", data)  # Add this line for debugging
    except FileNotFoundError:
        data = []


def save_data_to_file():
    with open(json_location, "w") as file:
        # Use 'indent' parameter for pretty formatting
        json.dump(data, file, indent=2)


def get_park_name(park_id):
    return RecreationClient.get_park_name(park_id)


def extract_campground_id(url):
    parsed_url = urlparse(url)
    path = parsed_url.path
    campground_id = path.split("/")[-1]
    return campground_id


if __name__ == "__main__":
    load_data_from_file()
    app.run(host="0.0.0.0", port=5001)
