const data = [];

const dateRangeInput = document.getElementById("date-range");
const picker = new Litepicker({
  element: dateRangeInput,
  singleMode: false,
  format: "YYYY-MM-DD",
  onSelect: (start, end) => {
    if (!end || start.getTime() === end.getTime()) {
      end = new Date(start.getTime());
      end.setDate(end.getDate() + 1);
    }
    picker.setDateRange(start, end, false); // Update the date range without triggering onSelect again

    // Update the input value directly
    dateRangeInput.value =
      start.format("YYYY-MM-DD") + " - " + end.format("YYYY-MM-DD");
  },
});

const createCampgroundCard = (entry) => {
  const card = document.createElement("div");
  card.classList.add(
    "bg-white",
    "text-gray-800",
    "rounded-xl",
    "p-4",
    "mb-4",
    "shadow-md",
    "relative"
  );

  const removeButton = document.createElement("button");
  removeButton.classList.add("remove-button");
  removeButton.innerHTML = "&times;";
  // Use entry.id instead of index
  removeButton.addEventListener("click", () => removeEntry(entry.id));

  const campgroundTitle = document.createElement("div");
  campgroundTitle.classList.add("text-center", "mb-2");

  // Create an anchor element for the campsite name
  const campsiteLink = document.createElement("a");
  campsiteLink.href = entry.campground_url;
  campsiteLink.target = "_blank"; // Open link in a new tab
  campsiteLink.textContent = entry.campground_name;

  // Append the campsite link to the campground title
  campgroundTitle.appendChild(campsiteLink);
  card.appendChild(removeButton);
  card.appendChild(campgroundTitle);

  const dateContainer = document.createElement("div");
  dateContainer.classList.add("text-center", "mb-2");
  const dateRange = document.createElement("span");
  dateRange.textContent = `${getDate(entry.start_date)} - ${getDate(
    entry.end_date
  )}`;
  dateContainer.appendChild(dateRange);
  card.appendChild(dateContainer);

  return card;
};

const getDate = (date) => {
  const options = {
    day: "numeric",
    month: "short",
    year: "numeric",
    weekday: "short",
  };
  const dateObject = new Date(date);
  dateObject.setMinutes(
    dateObject.getMinutes() + dateObject.getTimezoneOffset()
  );
  const formattedDate = dateObject.toLocaleDateString("en-US", options);
  return formattedDate;
};

const renderCampgroundContainer = () => {
  const container = document.getElementById("campground-container");
  container.innerHTML = "";

  // Sort the data by start_date in ascending order
  const sortedData = data.sort(
    (a, b) => new Date(a.start_date) - new Date(b.start_date)
  );

  // Group entries by month and year, and then by campground name
  const groupedEntries = sortedData.reduce((groups, entry) => {
    const monthYear = getMonthYear(entry.start_date);
    const campgroundName = entry.campground_name;

    if (!groups[monthYear]) {
      groups[monthYear] = {};
    }

    if (!groups[monthYear][campgroundName]) {
      groups[monthYear][campgroundName] = [];
    }

    groups[monthYear][campgroundName].push(entry);
    return groups;
  }, {});

  // Iterate through the month-year groups
  Object.entries(groupedEntries).forEach(([monthYear, campgrounds]) => {
    const monthYearTitle = document.createElement("h2");
    monthYearTitle.classList.add("text-xl", "font-bold", "mb-4");
    monthYearTitle.textContent = monthYear;
    container.appendChild(monthYearTitle);

    // Iterate through the campground groups within the current month-year group
    Object.entries(campgrounds).forEach(([campgroundName, entries]) => {
      const card = document.createElement("details");
      card.classList.add(
        "bg-white",
        "text-gray-800",
        "rounded-xl",
        "p-4",
        "mb-4",
        "shadow-md"
      );

      const campgroundTitle = document.createElement("summary");
      campgroundTitle.classList.add("text-center", "mb-2", "cursor-pointer");

      // Create an anchor element for the campsite name
      const campsiteLink = document.createElement("a");
      campsiteLink.href = entries[0].campground_url; // Assuming all entries have the same URL
      campsiteLink.target = "_blank"; // Open link in a new tab
      campsiteLink.textContent = campgroundName;

      // Append the campsite link to the campground title
      campgroundTitle.appendChild(campsiteLink);
      card.appendChild(campgroundTitle);

      entries.forEach((entry, index) => {
        const dateRemoveContainer = document.createElement("div");
        dateRemoveContainer.classList.add(
          "flex",
          "justify-between",
          "items-center",
          "mb-2"
        );

        const dateContainer = document.createElement("div");
        const dateRange = document.createElement("span");
        dateRange.textContent = `${getDate(entry.start_date)} - ${getDate(
          entry.end_date
        )}`;
        dateContainer.appendChild(dateRange);

        const removeButton = document.createElement("button");
        removeButton.classList.add("remove-button");
        removeButton.innerHTML = "&times;";
        removeButton.addEventListener("click", () => removeEntry(entry.id));
        dateRemoveContainer.appendChild(dateContainer);
        dateRemoveContainer.appendChild(removeButton);
        card.appendChild(dateRemoveContainer);
      });

      container.appendChild(card);
    });
  });
};

const getMonthYear = (date) => {
  const options = { month: "long", year: "numeric" };
  const formattedDate = new Date(date).toLocaleDateString("en-US", options);
  return formattedDate.toUpperCase();
};

document
  .getElementById("add-entry-form")
  .addEventListener("submit", async function (e) {
    e.preventDefault(); // Prevent the default form submission behavior

    const startDate = picker.getStartDate().format("YYYY-MM-DD");
    const endDate = picker.getEndDate().format("YYYY-MM-DD");
    const campgroundUrl = document.getElementById("campground-url").value;
    await addEntry(startDate, endDate, campgroundUrl);
    picker.setDateRange(null, null);
    e.target.reset();
  });

const addEntry = async (startDate, endDate, campgroundUrl) => {
  if (startDate === endDate) {
    const date = new Date(endDate);
    date.setDate(date.getDate() + 1); // Add one day to the end date
    endDate = date.toISOString().split("T")[0];
  }
  try {
    // Generate a unique ID using the current date and time
    const uniqueId = new Date().getTime().toString();

    const response = await fetch("/add_entry", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        id: uniqueId, // Include the unique ID in the JSON payload
        start_date: startDate,
        end_date: endDate,
        campground_url: campgroundUrl,
      }),
    });

    if (!response.ok) {
      throw new Error("Failed to add entry");
    }

    await fetchData();
  } catch (error) {
    console.error("Error adding entry:", error);
  }
};

const fetchData = async () => {
  try {
    const response = await fetch("/get_data");
    const fetchedData = await response.json();
    data.length = 0;
    Array.prototype.push.apply(data, fetchedData);
    renderCampgroundContainer();
  } catch (error) {
    console.error("Error fetching data:", error);
  }
};

const removeEntry = async (id) => {
  try {
    const response = await fetch("/remove_entry", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      // Send the id instead of the index
      body: JSON.stringify({ id: id }),
    });

    if (!response.ok) {
      throw new Error("Failed to remove entry");
    }

    await fetchData();
  } catch (error) {
    console.error("Error removing entry:", error);
  }
};

fetchData();
