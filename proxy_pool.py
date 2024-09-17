from bs4 import BeautifulSoup
import pandas as pd
from datetime import timedelta
import requests


# parse time strings for free proxy list
def parse_time_string(time_str):
    # Convert time string to seconds
    total_seconds = 0
    parts = time_str.split()
    
    for i in range(0, len(parts), 2):
        if i + 1 < len(parts):
            value = parts[i]
            unit = parts[i+1].lower()
            
            try:
                value = int(value)
            except ValueError:
                continue  # Skip if we can't convert to int
            
            if 'sec' in unit:
                total_seconds += value
            elif 'min' in unit:
                total_seconds += value * 60
            elif 'hour' in unit:
                total_seconds += value * 3600
            elif 'day' in unit:
                total_seconds += value * 86400
    
    return pd.Timedelta(seconds=total_seconds)

# parse free proxy table list and return as dataframe
def parse_proxy_table(content):
    # Check if content is already a BeautifulSoup object
    if isinstance(content, BeautifulSoup):
        soup = content
    else:
        # If it's not, assume it's an HTML string and parse it
        soup = BeautifulSoup(content, 'html.parser')
    
    # Find the table
    table = soup.find('table', {'class': 'table table-striped table-bordered'})
    
    # Extract table headers
    headers = [th.text for th in table.find_all('th')]
    
    # Extract table rows
    rows = []
    for tr in table.find_all('tr')[1:]:  # Skip the header row
        row = [td.text.strip() for td in tr.find_all('td')]
        rows.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(rows, columns=headers)
    
    # Clean up column names
    df.columns = df.columns.str.lower().str.replace(' ', '_')
    
    # Convert 'port' to integer
    df['port'] = pd.to_numeric(df['port'], errors='coerce').astype('Int64')
    
    # Convert 'last_checked' to timedelta
    df['last_checked'] = df['last_checked'].apply(lambda x: parse_time_string(x.replace(' ago', '')))
    
    return df

# selects best proxies from free proxy list and returns a pool
def select_best_proxies(df, max_age=timedelta(minutes=55), 
                        preferred_countries=['United States', 'Japan', 'France', 'Sweden', 'United Kingdom', 'Germany', 'Canada'],
                        anonymity_level='elite proxy', https_only=True, limit=50):
    """
    Filter and select the best proxies based on various criteria.
    
    :param df: DataFrame containing proxy information
    :param max_age: Maximum age of the proxy (as timedelta)
    :param preferred_countries: List of preferred countries
    :param anonymity_level: Preferred anonymity level
    :param https_only: If True, select only HTTPS proxies
    :param limit: Maximum number of proxies to return
    :return: List of JSON objects containing proxy information
    """
    # Convert 'last_checked' to timedelta if it's not already
    if not pd.api.types.is_timedelta64_dtype(df['last_checked']):
        df['last_checked'] = pd.to_timedelta(df['last_checked'])
    
    # Filter by age
    df = df[df['last_checked'] <= max_age]
    
    # Filter by HTTPS
    if https_only:
        df = df[df['https'].str.lower() == 'yes']
    
    # Filter by country
    df = df[df['country'].isin(preferred_countries)]
    
    # Filter by anonymity level
    df = df[df['anonymity'].str.lower() == anonymity_level.lower()]
    
    # Sort by last checked (most recent first)
    df = df.sort_values('last_checked')
    
    # Select the top proxies
    top_proxies = df.head(limit)
    
    # Convert to list of JSON objects
    proxy_list = top_proxies.apply(lambda row: {
        'ip': row['ip_address'],
        'port': row['port'],
        'country': row['country'],
        'anonymity': row['anonymity'],
        'https': row['https'],
        'last_checked': str(row['last_checked'])
    }, axis=1).tolist()
    
    return proxy_list

def get_best_proxies():
    url = 'https://www.sslproxies.org/'
    
    # Fetch the content
    response = requests.get(url)
    content = response.text
    
    # Parse the proxy table
    soup = BeautifulSoup(content, 'html.parser')
    proxies_df = parse_proxy_table(soup)
    
    # Select the best proxies
    best_proxies = select_best_proxies(proxies_df)
    
    return best_proxies
