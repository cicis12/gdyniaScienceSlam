(() => {
  let schoolsPromise;

  const numberMap = {
    "1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v",
    "6": "vi", "7": "vii", "8": "viii", "9": "ix", "10": "x",
    "11": "xi", "12": "xii", "13": "xiii", "14": "xiv", "15": "xv",
    "16": "xvi", "17": "xvii", "18": "xviii", "19": "xix", "20": "xx"
  };

  function normalize(value) {
    return value
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/ł/g, "l")
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function getSchoolNumber(value) {
    const roman = value.match(/\b(xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)\b/i);
    if (roman) return roman[0].toLowerCase();

    const numeric = value.match(/\b(20|1[0-9]|[1-9])\b/);
    return numeric ? numberMap[numeric[0]] : null;
  }

  function loadSchools() {
    if (!schoolsPromise) {
      schoolsPromise = fetch("/static/RSPO.json")
        .then(response => {
          if (!response.ok) throw new Error("Nie udało się pobrać listy szkół.");
          return response.json();
        })
        .then(data => data.map(school => {
          const normalizedName = normalize(school.name);
          return {
            name: school.name,
            city: school.city,
            normalized_name: normalizedName,
            normalized_city: normalize(school.city),
            school_number: getSchoolNumber(normalizedName)
          };
        }));
    }
    return schoolsPromise;
  }

  function initializeSchoolAutocomplete(form) {
    const input = form.querySelector(".school");
    const results = input?.closest(".autocompleteConatainer")?.querySelector(".results");
    if (!input || !results || !window.Fuse) return;

    let schools = [];
    let requestId = 0;
    let fuse = null;

    loadSchools()
      .then(data => {
        schools = data;
        fuse = new Fuse(schools, {
          keys: [
            { name: "normalized_name", weight: 0.7 },
            { name: "normalized_city", weight: 0.3 }
          ],
          threshold: 0.42,
          ignoreLocation: true,
          minMatchCharLength: 2,
          shouldSort: true,
          includeScore: true
        });
        input.dispatchEvent(new Event("schooldataready"));
      })
      .catch(error => {
        console.error(error);
        results.textContent = "Lista szkół jest chwilowo niedostępna.";
      });

    function search() {
      const currentRequestId = ++requestId;
      const query = normalize(input.value);
      results.replaceChildren();
      if (query.length < 2) return;

      if (!fuse) {
        loadSchools().then(data => {
          if (currentRequestId === requestId) {
            schools = data;
            fuse = new Fuse(schools, {
              keys: [
                { name: "normalized_name", weight: 0.7 },
                { name: "normalized_city", weight: 0.3 }
              ],
              threshold: 0.42,
              ignoreLocation: true,
              minMatchCharLength: 2,
              shouldSort: true,
              includeScore: true
            });
            search();
          }
        }).catch(() => {});
        return;
      }

      const schoolNumber = getSchoolNumber(query);
      const searchQuery = schoolNumber
        ? query.replace(/\b(20|1[0-9]|[1-9]|xx|xix|xviii|xvii|xvi|xv|xiv|xiii|xii|xi|x|ix|viii|vii|vi|v|iv|iii|ii|i)\b/i, schoolNumber)
        : query;
      const matches = fuse.search(searchQuery)
        .filter(result => !schoolNumber || !result.item.school_number || result.item.school_number === schoolNumber)
        .slice(0, 6);

      for (const match of matches) {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "result-item";
        option.setAttribute("role", "option");
        option.textContent = `${match.item.name} - ${match.item.city}`;
        option.addEventListener("click", () => {
          input.value = option.textContent;
          results.replaceChildren();
        });
        results.append(option);
      }

      if (matches.length === 0) {
        const empty = document.createElement("div");
        empty.className = "result-empty";
        empty.textContent = "Nie znaleziono pasującej szkoły.";
        results.append(empty);
      }
    }

    input.addEventListener("input", search);
    input.addEventListener("schooldataready", search);
    document.addEventListener("click", event => {
      if (!input.closest(".autocompleteConatainer").contains(event.target)) {
        results.replaceChildren();
      }
    });
  }

  window.initializeSchoolAutocomplete = initializeSchoolAutocomplete;
})();
