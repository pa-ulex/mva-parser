import csv
import re
import os
import sys
import argparse
import math
from collections import defaultdict

try:
    from shapely.geometry import Polygon, Point
    SHAPELY_AVAILABLE = True
except ImportError:
    print("Shapely library not found. Falling back to basic centroid calculation.")
    SHAPELY_AVAILABLE = False

def read_csv_file(file_path):
    """
    Read the CSV file and return a list of dictionaries
    """
    data = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            print(f"CSV columns: {reader.fieldnames}")
            for row in reader:
                data.append(row)
        print(f"Read {len(data)} rows from CSV.")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return []
    
    return data

def parse_geometry(geometry_str):
    """
    Parse WKT geometry string and extract coordinates
    Format: POLYGON((lon1 lat1, lon2 lat2, ...))
    Returns a list of [lat, lon] pairs
    """
    if not geometry_str or not isinstance(geometry_str, str):
        return []
    
    try:
        # Check for POLYGON format
        poly_match = re.search(r'POLYGON\s*\(\((.*?)\)\)', geometry_str)
        if poly_match:
            coord_str = poly_match.group(1)
        else:
            # Try other format with double parentheses
            other_match = re.search(r'\(\((.*?)\)\)', geometry_str)
            if other_match:
                coord_str = other_match.group(1)
            else:
                return []
        
        pairs = coord_str.split(',')
        
        coords = []
        for pair in pairs:
            parts = pair.strip().split()
            if len(parts) >= 2:
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    if -180 <= lon <= 180 and -90 <= lat <= 90:  # Basic validation
                        coords.append([lat, lon])
                except (ValueError, IndexError):
                    continue
        
        # Need at least 3 points to form a polygon
        if len(coords) < 3:
            return []
        
        return coords
    
    except Exception as e:
        print(f"Error parsing geometry: {e}")
        return []

def decimal_to_dms(decimal_deg, is_latitude=True):
    """
    Convert decimal degrees to Topsky DMS format
    Returns a string in the format "N/S/E/W DDD.MM.SS.000"
    """
    is_negative = decimal_deg < 0
    decimal_deg = abs(decimal_deg)
    
    degrees = math.floor(decimal_deg)
    decimal_minutes = (decimal_deg - degrees) * 60
    minutes = math.floor(decimal_minutes)
    decimal_seconds = (decimal_minutes - minutes) * 60
    seconds = round(decimal_seconds)  # Round to nearest second
    
    # Handle rounding issues
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        degrees += 1
    
    # Format direction prefix
    if is_latitude:
        prefix = 'S' if is_negative else 'N'
    else:
        prefix = 'W' if is_negative else 'E'
    
    # Format to exactly match the Topsky format (including leading zeros)
    return f"{prefix}{degrees:03d}.{minutes:02d}.{seconds:02d}.000"

def format_altitude(altitude):
    """
    Format altitude as exactly 2 digits with spaces as needed
    for Topsky format
    """
    # Handle None or empty string
    if altitude is None or altitude == '':
        return None

    try:
        alt_int = int(float(altitude))
        if alt_int <= 0:
            return None

        # Convert to hundreds of feet
        alt_hundreds = alt_int // 100

        return str(alt_hundreds)

    except (ValueError, TypeError) as e:
        print(f"Error formatting altitude '{altitude}': {e}")
        return None

def generate_line_entries(polygons):
    """
    Generate LINE entries from polygons
    Each polygon is a list of [lat, lon] coordinates
    """
    line_entries = []
    
    for polygon in polygons:
        coords = polygon['coords']
        if not coords or len(coords) < 3:
            continue
        
        # Connect each point to the next, including last to first to close the polygon
        for i in range(len(coords)):
            lat1, lon1 = coords[i]
            lat2, lon2 = coords[(i + 1) % len(coords)]
            
            # Format coordinates in Topsky format
            lat1_str = decimal_to_dms(lat1, is_latitude=True)
            lon1_str = decimal_to_dms(lon1, is_latitude=False)
            lat2_str = decimal_to_dms(lat2, is_latitude=True)
            lon2_str = decimal_to_dms(lon2, is_latitude=False)
            
            # Create LINE entry
            line = f"LINE:{lat1_str}:{lon1_str}:{lat2_str}:{lon2_str}"
            line_entries.append(line)
    
    return line_entries

def calculate_centroid(coords):
    """
    Calculate the centroid of a polygon
    Input: List of [lat, lon] coordinates
    Output: [lat, lon] of centroid
    """
    if not coords or len(coords) < 3:
        return None
    
    try:
        if SHAPELY_AVAILABLE:
            # Convert to shapely polygon (swap lat/lon order for shapely)
            polygon = Polygon([(lon, lat) for lat, lon in coords])
            
            
            #Check if polygon is empty
            if polygon.is_empty:
                return None
            
            # Get the centroid point
            centroid = polygon.centroid
            
            # Check if centroid is inside the polygon
            if polygon.contains(centroid):
                return [centroid.y, centroid.x]  # Return as [lat, lon]
            
            # Fallback: move the centroid step by step towards a guaranteed inside point
            inside = polygon.representative_point()
            test_point = centroid
            for i in range(10):  # max 10 iterations
                midx = (test_point.x + inside.x) / 2
                midy = (test_point.y + inside.y) / 2
                test_point = Point(midx, midy)
                if polygon.contains(test_point):
                    return [test_point.y, test_point.x]

            # If everything fails, just return representative_point
            return [inside.y, inside.x]
        else:
            # Fall back to simple centroid calculation if Shapely is not available
            lat_sum = sum(c[0] for c in coords)
            lon_sum = sum(c[1] for c in coords)
            return [lat_sum / len(coords), lon_sum / len(coords)]
    
    except Exception as e:
        print(f"Error calculating centroid: {e}")
        # Fall back to simple centroid calculation
        lat_sum = sum(c[0] for c in coords)
        lon_sum = sum(c[1] for c in coords)
        return [lat_sum / len(coords), lon_sum / len(coords)]

def generate_text_entries(polygons):
    """
    Generate TEXT entries from polygons
    Each polygon has a 'coords' list of [lat, lon] and an 'altitude' value
    """
    text_entries = []
    
    for polygon in polygons:
        coords = polygon['coords']
        altitude = polygon['altitude']
        
        if not coords or len(coords) < 3:
            continue
        
        # Calculate centroid for text placement
        centroid = calculate_centroid(coords)
        if not centroid:
            continue
        
        # Format coordinates
        lat_str = decimal_to_dms(centroid[0], is_latitude=True)
        lon_str = decimal_to_dms(centroid[1], is_latitude=False)
        
        # Format altitude to ensure it's exactly 2 digits
        alt_str = format_altitude(altitude)
        if not alt_str:
            continue
        
        # Create TEXT entry
        text = f"TEXT:{lat_str}:{lon_str}:{alt_str}"
        text_entries.append(text)
    
    return text_entries

def convert_csv_to_topsky(csv_file, output_file, topsky_maps="both"):
    """
    Convert MVA CSV file to Topsky format with both Summer and Winter maps
    topsky_maps: "both" (default), "summer", or "winter"
    """
    # Read CSV data
    data = read_csv_file(csv_file)
    if not data:
        print("No data found in CSV file")
        return False
    
    # Process data into polygons for both warm and cold MVAs
    warm_polygons = []
    cold_polygons = []
    
    # Count of successfully processed rows for each map
    warm_count = 0
    cold_count = 0
    
    for i, row in enumerate(data):
        # Find geometry column (should be "_geometry")
        geometry_col = '_geometry'
        if geometry_col not in row:
            for col in row:
                if col and 'geometry' in col.lower():
                    geometry_col = col
                    break
        
        if geometry_col not in row or not row[geometry_col]:
            continue
        
        # Debug information
        if i < 5:  # Print first 5 rows for debugging
            print(f"Row {i+1} geometry: {row[geometry_col][:50]}...")  # Truncate for readability
            
            warm_val = row.get('LOWERLIMIT', '')
            cold_val = row.get('MRVA_COLD', '')
            
            print(f"Row {i+1} LOWERLIMIT: '{warm_val}' ({type(warm_val).__name__})")
            print(f"Row {i+1} MRVA_COLD: '{cold_val}' ({type(cold_val).__name__})")
            
            warm_fmt = format_altitude(warm_val)
            cold_fmt = format_altitude(cold_val)
            
            print(f"Row {i+1} Formatted LOWERLIMIT: '{warm_fmt}'")
            print(f"Row {i+1} Formatted MRVA_COLD: '{cold_fmt}'")
        
        # Parse geometry
        coords = parse_geometry(row[geometry_col])
        if not coords or len(coords) < 3:
            continue
        
        # Get altitude values directly from row dictionary
        warm_alt = row.get('LOWERLIMIT', '')
        cold_alt = row.get('MRVA_COLD', '')
        
        # Format altitude values for Topsky display
        warm_alt_fmt = format_altitude(warm_alt)
        cold_alt_fmt = format_altitude(cold_alt)
        
        # Use warm_alt as fallback for cold_alt and vice versa
        if warm_alt_fmt and not cold_alt_fmt:
            cold_alt_fmt = warm_alt_fmt
            cold_alt = warm_alt
        elif cold_alt_fmt and not warm_alt_fmt:
            warm_alt_fmt = cold_alt_fmt
            warm_alt = cold_alt
        
        # Skip if neither altitude is available after formatting
        if not warm_alt_fmt and not cold_alt_fmt:
            # Try to assign a default value if none is available
            warm_alt_fmt = "30"  # Default altitude if none specified
            cold_alt_fmt = "30"  # Default altitude if none specified
            warm_alt = "30"
            cold_alt = "30"
        
        # Add to warm polygons
        warm_polygons.append({
            'coords': coords,
            'altitude': warm_alt
        })
        warm_count += 1
        
        # Add to cold polygons
        cold_polygons.append({
            'coords': coords,
            'altitude': cold_alt
        })
        cold_count += 1
    
    print(f"Processed {warm_count} polygons for summer MVA")
    print(f"Processed {cold_count} polygons for winter MVA")
    
    # Write to output file
    try:
        # initialize to avoid reference errors
        warm_lines, warm_texts, cold_lines, cold_texts = [], [], [], []
        with open(output_file, 'w') as f:
            if topsky_maps in ("both", "summer"):
                # Generate LINE and TEXT entries for warm MVA
                warm_lines = generate_line_entries(warm_polygons)
                warm_texts = generate_text_entries(warm_polygons)
                
                print(f"Generated {len(warm_lines)} lines and {len(warm_texts)} texts for summer MVA")
                # Write Summer (Warm) MVA map
                f.write("MAP:MVA Germany Summer\n")
                f.write("FOLDER:MVA\n")
                f.write("COLOR:green\n")
                f.write("STYLE:Solid:1\n")

                # Write all LINE entries for warm MVA
                for line in warm_lines:
                    f.write(f"{line}\n")

                # Write all TEXT entries for warm MVA
                for text in warm_texts:
                    f.write(f"{text}\n")
                    
            if topsky_maps == "both":
                # Add a blank line between maps
                f.write("\n")
            
            if topsky_maps in ("both", "winter"):
                # Generate LINE and TEXT entries for cold MVA
                cold_lines = generate_line_entries(cold_polygons)
                cold_texts = generate_text_entries(cold_polygons)
                
                print(f"Generated {len(cold_lines)} lines and {len(cold_texts)} texts for winter MVA")
                # Write Winter (Cold) MVA map
                f.write("MAP:MVA Germany Winter\n")
                f.write("FOLDER:MVA\n")
                f.write("COLOR:green\n")
                f.write("STYLE:Solid:1\n")

                # Write all LINE entries for cold MVA
                for line in cold_lines:
                    f.write(f"{line}\n")

                # Write all TEXT entries for cold MVA
                for text in cold_texts:
                    f.write(f"{text}\n")
        
        if topsky_maps in ("both", "summer"):
            print(f"Summer Map: {len(warm_lines)} LINE entries and {len(warm_texts)} TEXT entries")
        if topsky_maps in ("both", "winter"):
            print(f"Winter Map: {len(cold_lines)} LINE entries and {len(cold_texts)} TEXT entries")
            
        if topsky_maps == "both":
            print(f"Successfully wrote both MVA maps in {output_file}")
        else:
            print(f"Successfully wrote {topsky_maps} MVA map in {output_file}")
        return True
    
    except Exception as e:
        print(f"Error writing to output file: {e}")
        return False

def main():
    """
    Main function for command-line operation
    """
    parser = argparse.ArgumentParser(description='Convert MVA CSV to Topsky format with Summer and Winter maps')
    parser.add_argument('input', help='Input CSV file')
    parser.add_argument('output', help='Output Topsky .txt file')
    parser.add_argument('--maps', choices=['both', 'summer', 'winter'], default='both', help='Choose which MVA map(s) to generate (default: both)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.isfile(args.input):
        print(f"Error: Input file '{args.input}' not found")
        return
    
    # Convert CSV to Topsky format
    convert_csv_to_topsky(args.input, args.output, topsky_maps=args.maps)

if __name__ == "__main__":
    main()