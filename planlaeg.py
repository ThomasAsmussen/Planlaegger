import streamlit as st
from ortools.sat.python import cp_model
import calendar

# Helper function to get all Sundays to Thursdays in a given month and year
def get_weekdays_in_month(year, month):
    weekdays = []
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        weekday = calendar.weekday(year, month, day)
        if weekday in [6, 0, 1, 2, 3]:  # Sunday = 6, Monday = 0, ..., Thursday = 3
            weekdays.append(day)
    
    return weekdays

# Helper function to get specific weekdays in the given month (e.g., all Mondays)
def get_days_of_week_in_month(year, month, weekday_name):
    day_name_to_index = {
        "sunday": 6,
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "torsdag": 3,
        "onsdag": 2,
        "tirsdag": 1,
        "mandag": 0,
        "søndag": 6
    }
    weekday_index = day_name_to_index[weekday_name.lower()]
    days = []
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        if calendar.weekday(year, month, day) == weekday_index:
            days.append(day)
    
    return days

# Function to parse dates (numeric, ranges, and weekday names)
def parse_dates(date_list, year, month):
    result_dates = []
    
    for date in date_list:
        # if isinstance(date, int):
        #     # Single numeric date
        #     result_dates.append(date)
        date = date.strip()  # Remove any leading/trailing whitespace
        
        if date.isdigit():
            # Single numeric date (now correctly identifies strings like "1" or "2")
            result_dates.append(int(date))
        elif '-' in str(date):
            # Date range (e.g., '3-9')
            start, end = map(int, date.split('-'))
            result_dates.extend(range(start, end + 1))
        elif isinstance(date, str) and date.lower() in ["sunday", "monday", "tuesday", "wednesday", "thursday", "torsdag", "onsdag", "tirsdag", "mandag", "søndag"]:
            # Day name (e.g., "Thursday")
            result_dates.extend(get_days_of_week_in_month(year, month, date))
    
    return result_dates

# Combine availability from different input sources
def combine_availability(available, unavailable, year, month):
    weekdays_in_month = get_weekdays_in_month(year, month)
    final_availability = {}

    for person in set(available.keys()).union(unavailable.keys()):
        available_dates = available.get(person, [])
        unavailable_dates = unavailable.get(person, [])
        parsed_available_dates = parse_dates(available_dates, year, month)
        parsed_unavailable_dates = parse_dates(unavailable_dates, year, month)

        if not parsed_available_dates:
            parsed_available_dates = weekdays_in_month

        final_available_dates = [
            day for day in parsed_available_dates 
            if day in weekdays_in_month and day not in parsed_unavailable_dates
        ]
        final_availability[person] = sorted(set(final_available_dates))

    return final_availability

# Scheduler function
def schedule_people(available_days, preferences, possible_days, limit_one_day_per_person):
    model = cp_model.CpModel()
    num_people = len(available_days)
    schedule = {day: model.NewIntVar(0, num_people - 1, f'schedule_{day}') for day in possible_days}

    # Constraint: Ensure unavailable dates are respected
    for person_idx, (person, avail_days) in enumerate(available_days.items()):
        for day in possible_days:
            if day not in avail_days:
                model.Add(schedule[day] != person_idx)

    preference_penalties = []

    # Add preference penalties (soft constraints for preferred days)
    for person_idx, (person, preferred_days) in enumerate(preferences.items()):
        for day in preferred_days:
            if day in possible_days:
                penalty_var = model.NewBoolVar(f'prefer_{person_idx}_{day}')
                model.Add(schedule[day] == person_idx).OnlyEnforceIf(penalty_var)
                preference_penalties.append(penalty_var)

    # Soft constraints: Ensure each person is assigned at least one day
    unassigned_penalties = []
    for person_idx, person in enumerate(available_days.keys()):
        assigned_days = [model.NewBoolVar(f'assigned_{person_idx}_{day}') for day in possible_days]
        for day, assigned in zip(possible_days, assigned_days):
            model.Add(schedule[day] == person_idx).OnlyEnforceIf(assigned)
            model.Add(schedule[day] != person_idx).OnlyEnforceIf(assigned.Not())
        
        # Create a Boolean variable to indicate if the person is assigned to at least one day
        has_assignment = model.NewBoolVar(f'has_assignment_{person_idx}')
        model.Add(sum(assigned_days) >= 1).OnlyEnforceIf(has_assignment)
        model.Add(sum(assigned_days) == 0).OnlyEnforceIf(has_assignment.Not())

        # Penalize if this person is not assigned at least one day
        unassigned_penalties.append(has_assignment.Not())

        # Check if this person should only be limited to 1 day
        if limit_one_day_per_person.get(person, False):
            model.Add(sum(assigned_days) <= 1)
        else:
            model.Add(sum(assigned_days) <= 2)

    # Add penalties to the objective function
    penalty_weight = 100  # Heavy penalty for not meeting the 'at least one day' requirement
    model.Minimize(sum(preference_penalties) + penalty_weight * sum(unassigned_penalties))

    # Solve the model
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.FEASIBLE or status == cp_model.OPTIMAL:
        return {day: list(available_days.keys())[solver.Value(schedule[day])] for day in possible_days}
    else:
        return None


# Streamlit app
def main():
    st.title("Scheduling App")

    # Sidebar for year and month input
    st.sidebar.header("Settings")
    year = st.sidebar.number_input("Year", value=2024)
    month = st.sidebar.number_input("Month (1-12)", value=10)
    
    # Option to limit days in the month (e.g., 1-10, 27-30)
    limit_days_input = st.sidebar.text_input("Limit overall days (e.g., 1-10, 27-30):", "")

    # Collect possible days (Sundays to Thursdays) in the month
    possible_days = get_weekdays_in_month(year, month)

    # Apply limit if input is not empty and correctly parsed
    if limit_days_input.strip():
        try:
            limit_days = parse_dates(limit_days_input.split(','), year, month)
            possible_days = [day for day in possible_days if day in limit_days]
        except Exception as e:
            st.sidebar.error(f"Error parsing limit days: {e}")
            possible_days = get_weekdays_in_month(year, month)  # Reset to default if parsing fails

    # Sidebar for managing the list of people
    st.sidebar.header("Manage People")
    people = st.sidebar.text_area("Enter names, separated by commas", "Philip, August, Frederik, Josefine, Amalie, Asta, Sofie A, Sofie G, Alberte, Sylvester, Cecilie, Julia, Thor, Thomas, Henriette")
    people_list = [person.strip() for person in people.split(',') if person.strip()]

    # Dictionaries to hold input data
    available = {}
    unavailable = {}
    preferences = {}
    limit_one_day_per_person = {}

    # Input availability, unavailability, and preferences for each person
    st.header("Availability, Unavailability, and Preferences")
    for person in people_list:
        with st.expander(f"{person}"):
            # Checkbox for limiting to 1 day
            limit_one_day_per_person[person] = st.checkbox(f"Limit {person} to only 1 day", key=f"limit_{person}")
            
            # Availability input
            available_input = st.text_area(f"Available dates (e.g., 1, 2, 6-11, Monday):", key=f"avail_{person}")
            available[person] = [item.strip() for item in available_input.split(',')] if available_input else []

            # Unavailability input
            unavailable_input = st.text_area(f"Unavailable dates (e.g., 3, 7-10, Thursday):", key=f"unavail_{person}")
            unavailable[person] = [item.strip() for item in unavailable_input.split(',')] if unavailable_input else []

            # Preferences input
            preferences_input = st.text_area(f"Preferred dates (e.g., 5, 12, 20):", key=f"pref_{person}")
            preferences[person] = [int(item.strip()) for item in preferences_input.split(',') if item.strip().isdigit()] if preferences_input else []

    # Combine availability
    available_days = combine_availability(available, unavailable, year, month)

    # Run the scheduler
    schedule = schedule_people(available_days, preferences, possible_days, limit_one_day_per_person)

    # Display the results
    st.header("Schedule")
    if schedule:
        st.write(f"Schedule for {calendar.month_name[month]} {year}:")
        for day, person in schedule.items():
            st.write(f"Day {day}: {person}")
        
        # Identify and display unoccupied days
        unoccupied_days = [day for day in possible_days if day not in schedule]
        if unoccupied_days:
            st.write("Unoccupied days:")
            for day in unoccupied_days:
                st.write(f"Day {day}")
    else:
        st.write("No feasible schedule could be generated.")
        st.write("Unoccupied days:")
        for day in possible_days:
            st.write(f"Day {day}")

if __name__ == "__main__":
    main()