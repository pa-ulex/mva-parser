#!/usr/bin/env python3
"""
MVA Parser for Topsky - Creates both Summer (Warm) and Winter (Cold) MVA maps
with proper altitude values and text positioning
"""

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
        # Convert to float, then to int (handles string decimals like "30.0")
        alt_float = float(altitude)
        
        # Reject zero or negative values
        if alt_float <= 0:
            return None
        
        # Convert to integer
        alt_int = int(alt_float)
        
        # Convert to string
        alt_str = str(alt_int)
        
        # Single digit values: add a leading space
        if len(alt_str) == 1:
            return f" {alt_str}"
        # Two-digit values: return as is
        elif len(alt_str) == 2:
            return alt_str
        # Values over 99: truncate to last 2 digits
        else:
            # Check if the last two digits are "00"
            if alt_str[-2:] == "00":
                # For large round numbers, return the first two significant digits
                if int(alt_str) % 100 == 0:
                    return alt_str[:2]
                else:
                    return alt_str[-2:]
            else:
                return alt_str[-2:]
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
            
            # Get the centroid point
            centroid = polygon.centroid
            
            # Check if centroid is inside the polygon
            if polygon.contains(centroid):
                return [centroid.y, centroid.x]  # Return as [lat, lon]
            else:
                # If centroid is outside, find a point inside the polygon
                if not polygon.is_empty:
                    point_on_surface = polygon.representative_point()
                    return [point_on_surface.y, point_on_surface.x]  # Return as [lat, lon]
                else:
                    # Fall back to simple center calculation
                    lat_sum = sum(coord[0] for coord in coords)
                    lon_sum = sum(coord[1] for coord in coords)
                    return [lat_sum / len(coords), lon_sum / len(coords)]
        else:
            # Fall back to simple centroid calculation if Shapely is not available
            lat_sum = sum(coord[0] for coord in coords)
            lon_sum = sum(coord[1] for coord in coords)
            return [lat_sum / len(coords), lon_sum / len(coords)]
    
    except Exception as e:
        print(f"Error calculating centroid: {e}")
        # Fall back to simple centroid calculation
        lat_sum = sum(coord[0] for coord in coords)
        lon_sum = sum(coord[1] for coord in coords)
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

def convert_csv_to_topsky(csv_file, output_file):
    """
    Convert MVA CSV file to Topsky format with both Summer and Winter maps
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
    
    # Generate LINE and TEXT entries for both maps
    warm_lines = generate_line_entries(warm_polygons)
    warm_texts = generate_text_entries(warm_polygons)
    
    cold_lines = generate_line_entries(cold_polygons)
    cold_texts = generate_text_entries(cold_polygons)
    
    print(f"Generated {len(warm_lines)} lines and {len(warm_texts)} texts for summer MVA")
    print(f"Generated {len(cold_lines)} lines and {len(cold_texts)} texts for winter MVA")
    
    # Write to output file
    try:
        with open(output_file, 'w') as f:
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
            
            # Add a blank line between maps
            f.write("\n")
            
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
        
        print(f"Successfully created Topsky MVA maps in {output_file}")
        print(f"Summer Map: {len(warm_lines)} LINE entries and {len(warm_texts)} TEXT entries")
        print(f"Winter Map: {len(cold_lines)} LINE entries and {len(cold_texts)} TEXT entries")
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
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.isfile(args.input):
        print(f"Error: Input file '{args.input}' not found")
        return
    
    # Convert CSV to Topsky format
    convert_csv_to_topsky(args.input, args.output)

if __name__ == "__main__":
    main()