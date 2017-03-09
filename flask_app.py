from flask import Flask, Response, request, render_template
from twilio import twiml
from lyft_rides.auth import ClientCredentialGrant
from lyft_rides.session import Session
from lyft_rides.client import LyftRidesClient
import googlemaps
from googlemaps import convert
import json
import re
import requests

#from m2x.client import M2XClient
#import openxc

gKey = googlemaps.Client(key='KEY')

USER_ACTIVE_PREFERENCE = False  # User prefers to incorporate biking and walking
USER_BIKING_MAX_TIME = 30       # XX minutes max biking one-way, default is 30 because first 30 minutes are free on Bay Area Bikeshare (Ford GoBike)
USER_WALKING_MAX_TIME = 30      # XX minutes max walking to bikeshare station
USER_TRANSIT_MAX_TIME = 60      # XX minutes max acceptable travel time using transit
USER_SOCIAL_PREFERENCE = True   # User prefers a social experience with rideshare / shuttle rides
USER_GENDER_PREFERENCE = False  # User is comfortable riding with people of either gender
HAS_BIKE = False                # User has a bicycle with them and does not want to use bikeshare

def cleanhtml(raw_html):
    cleaner = re.compile('<.*?>')
    clean = re.sub(cleaner, '', raw_html)
    return clean

def GoBikeDirections(USER_ORIGIN, USER_DESTINATION, USER_MODE):
    directionsText = []
    directions_result = gKey.directions(
        USER_ORIGIN,
        USER_DESTINATION,
        mode=USER_MODE,
        departure_time="now")
    for instruction in directions_result[0]['legs'][0]['steps']:
        directionsText.append(cleanhtml(instruction['html_instructions']) + ' for ' + str(instruction['distance']['text']))
    return directionsText

def LyftOption(USER_ORIGIN):
    # https://pypi.python.org/pypi/lyft_rides
    try:
        float(USER_ORIGIN[0])
        USER_ORIGIN_LAT = re.sub(r',.*', "", USER_ORIGIN)
        USER_ORIGIN_LON = re.sub(r'.*,', "", USER_ORIGIN)
        Lyft_Text = []
        YOUR_CLIENT_ID = 'CLIENTID'
        YOUR_CLIENT_SECRET = 'SECRET'
        YOUR_PERMISSION_SCOPES = 'public' # https://developer.lyft.com/docs/authentication
        auth_flow = ClientCredentialGrant(client_id=YOUR_CLIENT_ID, client_secret=YOUR_CLIENT_SECRET, scopes=YOUR_PERMISSION_SCOPES)
        session = auth_flow.get_session()
        client = LyftRidesClient(session)
        #response = client.get_ride_types(USER_ORIGIN) # Didn't work
        response = client.get_ride_types(USER_ORIGIN_LAT, USER_ORIGIN_LON)
        ride_types = response.json.get('ride_types')
        for i in ride_types:
            Lyft_Text.append(str(i['display_name'])+", seats: "+str(i['seats'])+", cost per mile: $"+str((float(i['pricing_details']['cost_per_mile'])/100)))
    #except:
    #    return "Issues Lyft stuffs"
    except ValueError:
        pass
    if (len(Lyft_Text)==0):
        try:
            LocationGeoCode = gKey.geocode(USER_ORIGIN)
            USER_ORIGIN_LAT = str(LocationGeoCode[0]['geometry']['location']['lat'])
            USER_ORIGIN_LON = str(LocationGeoCode[0]['geometry']['location']['lng'])
            Lyft_Text = []
            YOUR_CLIENT_ID = 'CLIENTID'
            YOUR_CLIENT_SECRET = 'SECRET'
            YOUR_PERMISSION_SCOPES = 'public' # https://developer.lyft.com/docs/authentication
            auth_flow = ClientCredentialGrant(client_id=YOUR_CLIENT_ID, client_secret=YOUR_CLIENT_SECRET, scopes=YOUR_PERMISSION_SCOPES)
            session = auth_flow.get_session()
            client = LyftRidesClient(session)
            response = client.get_ride_types(USER_ORIGIN_LAT, USER_ORIGIN_LON)
            ride_types = response.json.get('ride_types')
            for i in ride_types:
                Lyft_Text.append(str(i['display_name'])+", seats: "+str(i['seats'])+", cost per mile: $"+str((float(i['pricing_details']['cost_per_mile'])/100)))
        except:
            return "Error in Lyft query"
    return Lyft_Text

def GoBike(USER_ORIGIN, USER_DESTINATION, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, DIRECTIONS):
    ########### Match Network
    # List of networks
    # https://www.motivateco.com/use-our-data/
    Networks = [["Ford GoBike", "San Francisco, CA", "https://gbfs.bayareabikeshare.com/gbfs/en/station_status.json", "https://gbfs.bayareabikeshare.com/gbfs/en/station_information.json"],
               ["Citi Bike NYC", "New York City, New York", "https://gbfs.citibikenyc.com/gbfs/en/station_status.json", "https://gbfs.citibikenyc.com/gbfs/en/system_information.json"],
               ["Capital Bikeshare", "Washington, DC", "https://gbfs.capitalbikeshare.com/gbfs/en/station_status.json", "https://gbfs.capitalbikeshare.com/gbfs/en/station_information.json"],
               ["Divvy", "Chicago, Illinois", "https://gbfs.divvybikes.com/gbfs/en/station_status.json", "https://gbfs.divvybikes.com/gbfs/en/station_information.json"],
               ["Bike Share Toronto", "Toronto, ON", "https://gbfs.bikesharetoronto.com/gbfs/en/station_status.json", "https://gbfs.bikesharetoronto.com/gbfs/en/station_information.json"],
               ["Hubway", "Boston, MA", "https://gbfs.thehubway.com/gbfs/en/station_status.json", "https://gbfs.thehubway.com/gbfs/en/station_information.json"]]
    # Extract locations for Google Maps distance query
    Locations = [i[1] for i in Networks]
    # Google Maps distance query
    network_distance = gKey.distance_matrix(Locations, USER_ORIGIN, mode="driving")
    Min_Network = None
    Min_Time = 99999
    for i in range(0, len(Locations)):
        if ('duration' in network_distance['rows'][i]['elements'][0]):
            # If a network is at least within 5 hours to the user's current location, find the closest network
            if (network_distance['rows'][i]['elements'][0]['duration']['value'] < 5*60*60 and network_distance['rows'][i]['elements'][0]['duration']['value'] < Min_Time):
                Min_Time = network_distance['rows'][i]['elements'][0]['duration']['value']
                Min_Network = i
    if (Min_Network != None):
        try:
            # Issue is reading json files - maybe time to launch on AWS???
            station_status = json.loads((requests.get(Networks[Min_Network][2])).text)
            station_information = json.loads((requests.get(Networks[Min_Network][3])).text)
            stationInfo = []
            stationLocation = []
            unavailableStations = 0
        except:
            return "section 0.25 error"
        try:
            for i in range(0, len(station_status['data']['stations'])):
                if (station_status['data']['stations'][i]['num_bikes_available'] >= 2):
                    stationInfo.append(station_status['data']['stations'][i]['num_bikes_available'])
                    if (station_status['data']['stations'][i]['station_id'] == station_information['data']['stations'][i]['station_id']):
                        stationLocation.append(str(station_information['data']['stations'][i]['lat'])+','+str(station_information['data']['stations'][i]['lon']))
                    else:
                        for j in station_information['data']['stations']:
                            if (station_status['data']['stations'][i]['station_id'] == j['station_id']):
                                stationLocation.append(str(j['lat'])+','+str(j['lon']))
                else:
                    unavailableStations += 1
        except:
            return "section 0.5 error"
        try:
            # Query Google Maps to determine walking distance from user's location to the closest station
            GoBike_Distance_Walk = gKey.distance_matrix(stationLocation, USER_ORIGIN, mode="walking")
            Min_Walk = 99999;
            Min_Station = None;
            #Min_Station_Info = None;
            for i in range(0, len(station_status['data']['stations']) - unavailableStations):
                if ('duration' in GoBike_Distance_Walk['rows'][i]['elements'][0]):
                    if (GoBike_Distance_Walk['rows'][i]['elements'][0]['duration']['value'] < Min_Walk):
                        Min_Walk = GoBike_Distance_Walk['rows'][i]['elements'][0]['duration']['value']
                        Min_Station = GoBike_Distance_Walk['origin_addresses'][i]
                        #Min_Station_Info = stationInfo[i]
        except:
            return "Section 2 error"
        try:
            ########### CLOSEST DESTINATION BIKESHARE STATION
            return_stationInfo = []
            return_stationLocation = []
            return_blockedStations = 0
            for i in range(0, len(station_status['data']['stations'])):
                # Don't want the user to go to a station with either no availale docks currently
                # or a high probability of having zero bikes when the user reaches the station.
                # Thus, the rule set here is if there are at least two docks available, the
                # station is a candidate for the user to go to
                if (station_status['data']['stations'][i]['num_docks_available'] >= 2):
                    return_stationInfo.append(station_status['data']['stations'][i]['num_docks_available'])
                    # station_id's should match at index, but double check
                    if (station_status['data']['stations'][i]['station_id'] == station_information['data']['stations'][i]['station_id']):
                        return_stationLocation.append(str(station_information['data']['stations'][i]['lat'])+','+str(station_information['data']['stations'][i]['lon']))
                    else:
                        for j in station_information['data']['stations']:
                            if (station_status['data']['stations'][i]['station_id'] == j['station_id']):
                                return_stationLocation.append(str(j['lat'])+','+str(j['lon']))
                else:
                    return_blockedStations += 1
            # Query Google Maps to determine walking distance from end destination to end location
            return_GoBike_Distance_Walk = gKey.distance_matrix(return_stationLocation, USER_DESTINATION, mode="walking")
            return_Min_Walk = 99999;
            return_Min_Station = None;
            #return_Min_Station_Info = None;
            for i in range(0, len(station_status['data']['stations']) - return_blockedStations):
                if (return_GoBike_Distance_Walk['rows'][i]['elements'][0]['duration']['value'] < return_Min_Walk):
                    return_Min_Walk = return_GoBike_Distance_Walk['rows'][i]['elements'][0]['duration']['value']
                    return_Min_Station = return_GoBike_Distance_Walk['origin_addresses'][i]
                    #return_Min_Station_Info = stationInfo[i]
        except:
            return "Section 3 error"
        try:
            ########### Bicycling time
            trip_GoBike_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="bicycling")
            CyclingDistance = trip_GoBike_Distance['rows'][0]['elements'][0]['distance']['text']
            CyclingDuration = trip_GoBike_Distance['rows'][0]['elements'][0]['duration']['text']
            # Set Min_Walk as total walking time to start station and from end station
            # Min_Station is the start station to go to
            # return_Min_Station is the end station to go to
            # Min_Station_Info
            if ((trip_GoBike_Distance['rows'][0]['elements'][0]['duration']['value']/60) > USER_BIKING_MAX_TIME or
               ((Min_Walk + return_Min_Walk)/60) > USER_WALKING_MAX_TIME):
                if (DIRECTIONS == "No Directions"):
                    return "WARNING: HIGH TRAVEL TIME, Use "+str(Networks[Min_Network][0])+". Your closest station is: "+str(Min_Station)+", a "+str(Min_Walk/60)+" minute walk. Bike for "+str(CyclingDuration)+" minutes to reach "+str(return_Min_Station)+", a "+str(return_Min_Walk/60)+" minute walk from "+str(USER_DESTINATION)
                elif (DIRECTIONS == "Directions"):
                    return ["WARNING: HIGH TRAVEL TIME, Use "+str(Networks[Min_Network][0])+". Your closest station is: "+str(Min_Station)+", a "+str(Min_Walk/60)+" minute walk. Bike for "+str(CyclingDuration)+" minutes to reach "+str(return_Min_Station)+", a "+str(return_Min_Walk/60)+" minute walk from "+str(USER_DESTINATION), "Directions from "+str(USER_ORIGIN)+" to "+str(Min_Station)+": "+str(GoBikeDirections(USER_ORIGIN, Min_Station, "walking"))+". Directions from "+str(Min_Station)+" to "+str(return_Min_Station)+": "+str(GoBikeDirections(Min_Station, return_Min_Station, "bicycling"))+". Directions from "+str(return_Min_Station)+" to "+str(USER_DESTINATION)+": "+str(GoBikeDirections(return_Min_Station, USER_DESTINATION, "walking"))]
                else:
                    return "Issue with directions command"
            if (DIRECTIONS == "No Directions"):
                return "Use "+str(Networks[Min_Network][0])+". Your closest station is: "+str(Min_Station)+", a "+str(Min_Walk/60)+" minute walk. Bike for "+str(CyclingDuration)+" minutes to reach "+str(return_Min_Station)+", a "+str(return_Min_Walk/60)+" minute walk from "+str(USER_DESTINATION)
            elif (DIRECTIONS == "Directions"):
                return ["Use "+str(Networks[Min_Network][0])+". Your closest station is: "+str(Min_Station)+", a "+str(Min_Walk/60)+" minute walk. Bike for "+str(CyclingDuration)+" minutes to reach "+str(return_Min_Station)+", a "+str(return_Min_Walk/60)+" minute walk from "+str(USER_DESTINATION), "Directions from "+str(USER_ORIGIN)+" to "+str(Min_Station)+": "+str(GoBikeDirections(USER_ORIGIN, Min_Station, "walking"))+". Directions from "+str(Min_Station)+" to "+str(return_Min_Station)+": "+str(GoBikeDirections(Min_Station, return_Min_Station, "bicycling"))+". Directions from "+str(return_Min_Station)+" to "+str(USER_DESTINATION)+": "+str(GoBikeDirections(return_Min_Station, USER_DESTINATION, "walking"))]
            else:
                return "Issue with directions command"
        except:
            return "Issue with parsing of "+str(Networks[Min_Network][0])+" feed"
    else:
        return "No known bikeshare networks in your area"

def ModeChoice(USER_ORIGIN, USER_DESTINATION, USER_ACTIVE_PREFERENCE, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME,
              USER_TRANSIT_MAX_TIME, USER_SOCIAL_PREFERENCE, USER_GENDER_PREFERENCE):
    # Set default mode to driving
    Mode = "driving"
    # Is the user okay with an active mode?
    if (USER_ACTIVE_PREFERENCE):
        # Query Google Maps API for walking time
        Walk_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="walking")
        # If walking is an acceptable option
        if (Walk_Distance['rows'][0]['elements'][0]['duration']['value']/60 < USER_WALKING_MAX_TIME and USER_ACTIVE_PREFERENCE):
            Mode = "walking"
            return str(Mode)+" with travel time: "+str(Walk_Distance['rows'][0]['elements'][0]['duration']['value']/60)+" minutes"
        # If biking is an option
        else:
            Bike_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="bicycling")
            if (Bike_Distance['rows'][0]['elements'][0]['duration']['value']/60 < USER_BIKING_MAX_TIME and HAS_BIKE):
                Mode = "bicycling"
                ####### NOW EVALUATE BIKESHARE OPTIONS
                return str(Mode)+" with distance: "+str(Bike_Distance['rows'][0]['elements'][0]['duration']['value']/60)+" minutes"
            elif (Bike_Distance['rows'][0]['elements'][0]['duration']['value']/60 < USER_BIKING_MAX_TIME and
                 re.search(r'WARNING',
                           GoBike(USER_ORIGIN, USER_DESTINATION, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, "No Directions")
                          )==None):
                Mode = "bikeshare"
                ####### NOW EVALUATE BIKESHARE OPTIONS
                return str(Mode)+": "+GoBike(USER_ORIGIN, USER_DESTINATION, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, "No Directions")
            else:
                Transit_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="transit")
                if (Transit_Distance['rows'][0]['elements'][0]['duration']['value']/60 < USER_TRANSIT_MAX_TIME):
                    return str(Mode)+" with travel time: "+str(Transit_Distance['rows'][0]['elements'][0]['duration']['value']/60)+" minutes"
                else:
                    Car_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="driving")
                    return str(Mode)+" with travel time: "+str(Car_Distance['rows'][0]['elements'][0]['duration']['value']/60)+" minutes. Consider Lyft: "+str(LyftOption(USER_ORIGIN))
    # If transit is an option
    else:
        Transit_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="transit")
        if (Transit_Distance['rows'][0]['elements'][0]['duration']['value']/60 < USER_TRANSIT_MAX_TIME):
            return str(Mode)+" with travel time: "+str(Transit_Distance['rows'][0]['elements'][0]['duration']['value']/60)+" minutes"
        else:
            Car_Distance = gKey.distance_matrix(USER_ORIGIN, USER_DESTINATION, mode="driving")
            return str(Mode)+" with travel time: "+str(Car_Distance['rows'][0]['elements'][0]['duration']['value']/60)+" minutes. Consider Lyft: "+str(LyftOption(USER_ORIGIN))

app = Flask(__name__)
app.config["DEBUG"] = True

@app.route("/")
def main():
	return render_template('index.html')

@app.route("/twilio", methods=["POST"])
def inbound_sms():
    response = twiml.Response()
    inbound_message = request.form.get("Body")
    if (re.search(r'\+|\?|\*|\^|\$|\(|\)|\[|\]|\{|\}', inbound_message)):
        response.message("Invalid characters in ride request")
    else:
        try:
            ####################################################################
            ############################## Bikeshare
            ####################################################################
            # Bikeshare|bikeshare from ORIGIN to DESTINATION [with directions]
            if (re.search(r'Bikeshare|bikeshare', inbound_message)):
                if (re.search(r'with directions', inbound_message)):
                    Location_Message = re.sub(r'Bikeshare from |bikeshare from ', "", inbound_message)
                    Location_Message = re.sub(r' with directions', "", inbound_message)
                    USER_ORIGIN = re.sub(r' to.*', "", Location_Message)
                    USER_DESTINATION = re.sub(r'.*to ', "", Location_Message)
                    GoBike_Result = GoBike(USER_ORIGIN, USER_DESTINATION, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, "Directions")
                    for i in GoBike_Result:
                        response.message(str(i))
                else:
                    Location_Message = re.sub(r'Bikeshare from |bikeshare from ', "", inbound_message)
                    USER_ORIGIN = re.sub(r' to.*', "", Location_Message)
                    USER_DESTINATION = re.sub(r'.*to ', "", Location_Message)
                    response.message(str(GoBike(USER_ORIGIN, USER_DESTINATION, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, "No Directions")))
            ####################################################################
            ############################## Assess Mode Options
            ####################################################################
            elif (re.search(r'Best|best', inbound_message)):
                #######
                ####### TODO: ADD SUPPORT FOR DIRECTIONS
                #######
                if (re.search(r'with directions', inbound_message)):
                    Location_Message = re.sub(r'Best option from |best option from ', "", inbound_message)
                    Location_Message = re.sub(r' with directions', "", inbound_message)
                    USER_ORIGIN = re.sub(r' to.*', "", Location_Message)
                    USER_DESTINATION = re.sub(r'.*to ', "", Location_Message)
                    response.message(str(ModeChoice(USER_ORIGIN, USER_DESTINATION, USER_ACTIVE_PREFERENCE, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, USER_TRANSIT_MAX_TIME, USER_SOCIAL_PREFERENCE, USER_GENDER_PREFERENCE)))
                else:
                    Location_Message = re.sub(r'Best option from |best option from ', "", inbound_message)
                    USER_ORIGIN = re.sub(r' to.*', "", Location_Message)
                    USER_DESTINATION = re.sub(r'.*to ', "", Location_Message)
                    response.message(str(ModeChoice(USER_ORIGIN, USER_DESTINATION, USER_ACTIVE_PREFERENCE, USER_BIKING_MAX_TIME, USER_WALKING_MAX_TIME, USER_TRANSIT_MAX_TIME, USER_SOCIAL_PREFERENCE, USER_GENDER_PREFERENCE)))
        except:
            response.message("invalid syntax")
    return Response(str(response), mimetype="application/xml"), 200