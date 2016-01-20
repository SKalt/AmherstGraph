# -*- coding: utf-8 -*-
"""
This module defines and runs functions which scrape the Amherst College
departmental course catalogs to create a file, data.json, which plugs
into the Oxford Internet Institute's interactive network viewer.  This
file contains the node and edge attributes of the network of prerequisites
at Amherst College: which courses are required by which.

Created on Mon Jan 11 13:26:45 2016

@author: steven
"""

# import block
from lxml import html
import urllib3 as ul
ul.disable_warnings()
HTTP = ul.PoolManager()
import io
import time
import re
import itertools
from datetime import date
import igraph
import json
import os
from random import randint
from collections import OrderedDict

#%%
def get_catalog_urls():
    """
    This function returns a list of departments' current course catalog URLs
    as current_catalog_urls, a list
    """
    # define address strings
    departments_url = "https://www.amherst.edu/academiclife/departments"
    majors_xpath = '//*[@id="node-214534"]/div/div[1]/div/div/ul/li/a/@href'
    
    # get the page info
    data = HTTP.request("GET", departments_url).data
    tree = html.parse(io.BytesIO(data))
    
    #get the urls of each major's course catalog
    majors_urls = tree.xpath(majors_xpath)
    current_catalog_urls = []
    for dept in majors_urls:
        current_catalog_urls.append("www.amherst.edu{}/courses".format(dept))
        
    # add architecture, which has a bad shortened url
    url = 'www.amherst.edu/academiclife/departments/architectural_studies/'
    url += 'courses'
    current_catalog_urls.append(url)
    
    return current_catalog_urls


def get_date(current_catalog_urls):
    """
    This gets the current year, uses it to name the previous academic year,
    and then creates a list of all the urls of course catalogs of each
    department for each semester in the current and past academic years.
    The automatic year-generation block may be replaceable with manual input,
    in case the user wishes to research a particular set of years.
    Returns catalog_urls, a list of department catalog urls for the last
    4 semesters
    """
    if date.today().month < 5:
        # it is in the spring
        year3 = date.today().year - 2000 # the current 2-digit year
        year2 = year3 - 1
        year1 = year2 -1
    else:
        # it is in the fall
        year2 = date.today().year - 2000 # the current 2-digit year
        year1 = year2 - 1 # the past year
        year3 = year2 + 1 # the year to come
    year1, year2, year3 = str(year1), str(year2), str(year3)

    # makes the url suffixes
    years_of_interest_0 = ['/' + year1+year2, '/' + year2+year3]
    years_of_interest = []
    for year in years_of_interest_0:
        years_of_interest .append(year + 'F')
        years_of_interest .append(year + 'S')
    
    # makes catalog_urls, the list of all the department catalog URLs of
    # interest
    catalog_urls = []
    for i in current_catalog_urls:
        for j in years_of_interest:
            catalog_urls.append(i + j)
    return catalog_urls


def get_courses(catalog_urls):
    """
    This function returns a dictionary, course_urls, mapping departments
    to the urls of the courses they include.
    """
    # define the xpath address, dict to hold the results
    path = '//*[@id="academics-course-list"]/' + \
        'div[contains(@class, "coursehead")]/a/@href'
    course_urls = {}
    
    # get all courses' urls from each major's catalog, recording their origins
    for url in catalog_urls:
        try:
            # BCBP is an exception...
            if 'mm/177295' in url:
                url.replace('mm/177295', \
                            'academiclife/departments/' + \
                            'biochemistry-biophysics/courses')
            dept = url.split('/')[3]
            request = HTTP.request("GET", url).data
            tree = html.parse(io.BytesIO(request))
            if dept not in course_urls.keys():
                course_urls[dept] = []
            course_url = ['www.amherst.edu' + x for x in tree.xpath(path)]
            course_urls[dept] += course_url
        except KeyError:
            print(url + '!')
    return course_urls

def get_related_courses(dept_string):
    """
    Finds the department curriculum page of a specified department, then
    returns a list of course codes related to the major, related_course_codes
    """
    x1 = '//*[@id="acad-rltd-crs"]/div/text()'
    x2 = '//*[@id="acad-rltd-crs"]/div/a/text()'
    related_course_codes = []
    for url in CATALOG_URLS:
        if dept_string in url:
            r = HTTP.request('GET', url + '?display=curriculum')
            print(r.status)
            tree = html.parse(io.BytesIO(r.data))
            related_courses = tree.xpath(x1) + tree.xpath(x2)
            related_course_codes += [title[0:8] for title in related_courses]
    related_course_codes = list(set(related_course_codes))
    return(related_course_codes)
    

def get_most_recent_course_urls(course_urls):
    """
    This function returns a list of the urls of the most recent iterations of
    all the courses observed
    """
    # make a non-unique list of all the course urls
    recent_course_urls = itertools.chain(*[x[1] for x in course_urls.items()])
    
    # make a unique list of all the course urls
    unique_course_urls = list(set(list(recent_course_urls)))
    unique_courses = []
    for url in unique_course_urls:
        repetitions = '-'.join(url.split('/')[::-1][0].split('-')[0:2])
        unique_courses.append(repetitions)
    unique_courses = list(set(unique_courses))

    # make a list of all the most recent course urls
    unique_recent_urls = []
    for code in unique_courses:
        course_urls_list = [url for url in unique_course_urls if code in url]
        dates = []
        for url in course_urls_list:
            year = int(url[len(url) - 3:len(url) - 1])
            if url[len(url)-1:] == 'S':
                year += .1
            dates.append(year)
        for i in enumerate(dates):
            if i[1] == max(dates):
                unique_recent_urls.append(course_urls_list[i[0]])
    return unique_recent_urls


def get_course_info(unique_recent_urls, course_urls):
    """
    This chunk creates a dictionary, course_details, with the following
    format:
    {"CNUM-000":{ "departments" : a list of department codes (for partitioning
                              the nodes in the visualisation),
                 "url"    : a string linking to the course description in
                            another tab (for display in the visualisation as
                             a node attribute)
                 "rline"  : a string of the course title (the label of each
                            node inthe visualization)
                }
    """
    # start timing
    time_0 = time.time()

    # get a dict of course details
    course_details = {}
    path = '//*[@id="academics-course-list"]/p/text()'

    for url in unique_recent_urls:
        tree = html.parse(io.BytesIO(HTTP.request('GET', url).data))
        try:
            description = [t for t in tree.xpath(path) if 'Requisite:' not in t]
            description = '\n'.join(description)
        except IndexError:
            print(t)
        reqline = [t for t in tree.xpath(path) if 'Requisite:' in t]
        code = '-'.join(url.split('/')[::-1][0].split('-')[0:2])
        depts = [key for key, value in course_urls.items() if url in value]
        try:
            title = tree.xpath('//*[@id="academics-course-list"]/h2/text()')
            title = title[0]
        except IndexError:
            title = code
        course_details[code] = {"url": 'http://' + url,
                                "departments": depts,
                                "description": description,
                                "rline": reqline,
                                "title": title}
    print(time.time() - time_0)
    return course_details


def get_prereqs(course_details):
    """
    This function creates a dictionary, prereqs, mapping each course code to
    the required courses it names in its  online course description.
    """
    prereqs = []
    # search the line describing requirements for course codes
    for k in course_details.keys():
        rline = course_details[k]["rline"]
        if len(rline) > 0:
            rline = rline[0]
            rline = rline.replace(u'\xa0', u' ')
            words = re.split(' |-|,|/|;|\.', rline)
            # assume a course is most likely to require another in its own
            # department
            current_dept = k[0:4]
            for word in words:
                if word.upper() in DEPTS:
                    current_dept = word
                if word.isnumeric() and len(word) == 3:
                    # add a (prereq, course) tuple to the edgelist
                    prereq = current_dept + '-' + word
                    prereqs.append((prereq, k))
    return prereqs


def test_prereqs(prereqs, course_details):
    """
    This function tests the edgelist of prereq relationships, displaying lines
    explaining requirements which do not contain any course numbers
    """
    targets = [pair[1] for pair in prereqs]
    for k in course_details.keys():
        if k not in targets:
            if len(course_details[k]["rline"]) > 0:
                print(course_details[k]["rline"])


def make_course_graph(course_details, prereqs):
    """
    Makes an igraph Graph object, complete_course_graph, from the edgelist of
    prerequisite relations and the total number of courses and makes the
    object global.
    """
    # count the number of required courses not in 'course_details'
    all_courses = itertools.chain(*prereqs)
    extra_courses = [c for c in all_courses if c not in course_details.keys()]
    number_of_courses = len(extra_courses) + len(course_details)
    
    # create an empty graph with all the courses as nodes, then add prereq
    # relations from the prereqs edgelist
    names_of_courses = list(course_details.keys()) + extra_courses
    complete_course_graph = igraph.Graph(number_of_courses, directed=True)
    complete_course_graph.vs["name"] = names_of_courses
    complete_course_graph.add_edges(prereqs)
    return complete_course_graph

def make_subgraph(dept_string, course_details, complete_course_graph):
    """
    takes a department string, and finds all courses in this department or
    required by the department, and create a new igraph object from these
    courses and their relationships.

    Here are the current dept_strings:
     'art',	 'Biology',	 'sexuality_womens_gender_studies'
     'ljst',	 'physics',	 'biochemistry-biophysics',
     'film',	 'russian',	 'anthropology_sociology',
     'asian',	 'classics',	 'environmental_studies',
     'music',	 'religion',	 'architectural_studies',
     'french',	 'chemistry',	 'political_science',
     'german',	 'astronomy',	 'computer_science',
     'history',	 'economics',	 'american_studies',
     'english',	 'psychology',	 'european_studies',
     'geology',	 'philosophy',	 'black_studies',
     'spanish',	 'mathematics',	 'theater_dance',
     'courses',	 'neuroscience'
    """
    # get a list of courses relevant to the department
    relevant_courses = []
    for k in course_details.keys():
        if dept_string in course_details[k]["departments"]:
            relevant_courses.append(k)
    related_courses = get_related_courses(dept_string)
    for code in related_courses:
        if code in course_details.keys():
            relevant_courses.append(k)
        

    # get the vertex ids of the relevant courses
    relevant_course_vertex_ids = []
    for course in relevant_courses:
        vertex_id = complete_course_graph.vs["name"].index(course)
        relevant_course_vertex_ids.append(vertex_id)

    # make a graph containing all courses requiring or required by these
    # courses
    neighbors = complete_course_graph.neighborhood(relevant_course_vertex_ids)
    neighbors = neighbors = [i for i in itertools.chain(*neighbors)]
    subgraph = complete_course_graph.induced_subgraph(neighbors)
    return subgraph

def get_sugiyama_layout(subgraph):
    """
    This function sorts a prerequisites graph into 100,200,300, and 400-level
    classes, then returns the x and y positions of each node in that layout
    """
    # get a list of course levels corresponding to each course-node
    course_levels = []
    for course_name in subgraph.vs["name"]:
        for letter in course_name:
            if letter.isnumeric():
                course_levels.append(int(letter))
                break

    # get the layout object
    sugiyama_layout = subgraph.layout_sugiyama(layers=course_levels, \
                                               maxiter=1000)
    sugiyama_layout = sugiyama_layout[0:subgraph.vcount()]
    return sugiyama_layout

def make_color():
    "returns a number between 0 and 255"
    return randint(0, 255)


def get_rgb():
    "returns a tuple of three numbers between 0 and 255"
    return (make_color(), make_color(), make_color())


def make_json(dept_string, course_details, complete_course_graph):
    """
    This function makes a JSON object called 'data', to be inserted
    into the directory exported by a sigma.js template (named 'network') to
    make an interactive web visualization of the prereqs network
    """
    data = {"edges":[], "nodes":[]}
    
    #get the subgraph, node positions
    subgraph = make_subgraph(dept_string, \
                             course_details, \
                             complete_course_graph)
    sugiyama_layout = get_sugiyama_layout(subgraph)

    unique_departments = [name[0:4] for name in subgraph.vs["name"]]
    department_colors = {dept:get_rgb() for dept in unique_departments}

    for node in enumerate(subgraph.vs["name"]):
        if node[1] in course_details.keys():
            node_output = OrderedDict()
            node_output["label"] = node[1]
            node_output["x"] = sugiyama_layout[node[0]][0]
            node_output["y"] = sugiyama_layout[node[0]][1]
            node_output["id"] = str(node[0])
            node_output["attributes"] = OrderedDict()
            node_output["attributes"]["Title"] = course_details[\
                node[1]]["title"]
            node_output["attributes"]["Description"] = \
                course_details[node[1]]["description"]
            node_output["attributes"]["Department Code"] = node[1][0:4]
            node_output["attributes"]["Course Site"] = "<a href= '" + \
                course_details[node[1]]["url"] + "'> Course Site </a>"
            node_output["attributes"]["Requisite"] = \
                course_details[node[1]]["rline"]
            node_output["color"] = 'rgb' + str(department_colors[node[1][0:4]])
            node_output["size"] = 10.0 
        # if the course has no retrieved details:
        else:
            node_output = OrderedDict()
            node_output["label"] = node[1]
            node_output["x"] = sugiyama_layout[node[0]][0]
            node_output["y"] = sugiyama_layout[node[0]][1]
            node_output["id"] = str(node[0])
            node_output["attributes"] = OrderedDict()
            node_output["attributes"]["Title"] = node[1]
            node_output["attributes"]["Description"] = 'not offered in the' + \
                " last 4 semesters"
            node_output["attributes"]["Department Code"] = node[1][0:4]
            node_output["attributes"]["Course Site"] = ""
            node_output["attributes"]["Requisite"] = ''
            node_output["color"] = 'rgb' + str(department_colors[node[1][0:4]])
            node_output["size"] = 10.0
        data["nodes"].append(node_output)

    edgelist = subgraph.get_edgelist()
    for edge in enumerate(edgelist):
        color = department_colors[subgraph.vs["name"][edge[1][1]][0:4]]
        color = 'rgb' + str(color)
        edge_output = OrderedDict()
        edge_output["label"] = ''
        edge_output["source"] = str(edge[1][0])
        edge_output["target"] = str(edge[1][1])
        edge_output["id"] = str(len(node_output) - 1 + 2*edge[0])
        # this is to conform with the odd indexing I see in working 
        # visualisations
        edge_output["attributes"] = {}
        edge_output["color"] = color # target node color
        edge_output["size"] = 1.0
        data["edges"].append(edge_output)
    return data


def find_or_make_directory_address(dept_string):
    """
    finds whether there is a directory named after a deptarment string, and
    if not, makes one
    """
    directory = './'+ dept_string
    if not os.path.exists(directory):
        os.makedirs(directory)
    return directory


def export_json(dept_string, course_details, complete_course_graph):
    """
    writes the data json object describing a major's prerequisite network to
    a file called 'data.json' in a directory named after the department
    """
    data = make_json(dept_string, course_details, complete_course_graph)
    path = find_or_make_directory_address(dept_string)
    path += '/data.json'
    json_file = json.dumps(data, separators=(',', ':'))
    target_file = open(path, 'w')
    target_file.write(json_file)
    target_file.close()

#%%
#This chunk creates a dictionary mapping the long-form deparment names
#found in their departmental catalog urls and so in the course_urls
#dictionary to the four-digit departmental codes used elsewhere

DEPT_CODES = {'Biology':                         'BIOL',
              'american_studies':                'AMST',
              'anthropology_sociology':          'ANTH', # or SOCI
              'architectural_studies':           'ARCH',
              'art':                             'ARHA',
              'asian':                           'ASLC',
              'astronomy':                       'PHYS',
              'biochemistry-biophysics':         'BCBP',
              'black_studies':                   'BLST',
              'chemistry':                       'CHEM',
              'classics':                        'CLAS',
              'computer_science':                'COSC',
              'economics':                       'ECON',
              'english':                         'ENGL',
              'environmental_studies':           'ENST',
              'european_studies':                'HIST',
              'film':                            'FILM',
              'french':                          'FREN',
              'geology':                         'GEOL',
              'german':                          'GERM',
              'history':                         'HIST',
              'ljst':                            'LJST',
              'mathematics':                     'MATH',
              'music':                           'MUSI',
              'neuroscience':                    'NEUR',
              'philosophy':                      'PHIL',
              'physics':                         'PHYS',
              'political_science':               'POSC',
              'psychology':                      'PSYC',
              'religion':                        'RELI',
              'russian':                         'RUSS',
              'sexuality_womens_gender_studies': 'SWAG',
              'spanish':                         'SPAN',
              'theater_dance':                   'THDA'}

DEPTS = ['GEOL', 'AMST', 'PSYC', 'FREN', 'FILM', 'STAT',
         'CHEM', 'MUSI', 'FAMS', 'ANTH', 'HIST', 'POSC',
         'SOCI', 'ARCH', 'ARAB', 'BIOL', 'GREE', 'EUST',
         'PHYS', 'BCBP', 'SWAG', 'NEUR', 'CLAS', 'SPAN',
         'COSC', 'BLST', 'ENST', 'GERM', 'PHIL', 'LATI',
         'ENGL', 'ARHA', 'CHIN', 'LJST', 'MATH', 'ASTR',
         'THDA', 'RUSS', 'RELI', 'ECON', 'JAPA', 'ASLC']

## how I obtained these lists:
#dept_codes = {}
#for k in course_urls.keys():
#    dept_codes[k] = max(set([u.split('/')[5] for u in course_urls[k]]),
#                         key=[u.split('/')[5] for u in course_urls[k]].count)
#    print(k)
#    print([u.split('/')[5] for u in course_urls[k]])
#    print(max(set([u.split('/')[5] for u in course_urls[k]]),
#                  key=[u.split('/')[5] for u in course_urls[k]].count))
#dept_codes['classics'] = 'CLAS'
#dept_codes['asian'] = 'ASLC'
#dept_codes['film'] = 'FILM'
#dept_codes['biochemistry-biophysics'] = dept_codes['courses']
#dept_codes['biochemistry-biophysics'] = 'BCBP'
#
#for k in course_urls.keys():
#    for url in course_urls[k]:
#        dept_code = url.split('/')[5]
#        depts.append(dept_code)
#depts = list(set(depts))
#%% run the code
if __name__ == "__main__":
    CURRENT_CATALOG_URLS = get_catalog_urls()
    CATALOG_URLS = get_date(CURRENT_CATALOG_URLS)
    COURSE_URLS = get_courses(CATALOG_URLS)
    UNIQUE_RECENT_URLS = get_most_recent_course_urls(COURSE_URLS)
    COURSE_DETAILS = get_course_info(UNIQUE_RECENT_URLS, COURSE_URLS)
    PREREQS = get_prereqs(COURSE_DETAILS)
    test_prereqs(PREREQS, COURSE_DETAILS)
    COMPLETE_COURSE_GRAPH = make_course_graph(COURSE_DETAILS, PREREQS)
    for temp_dept_string in DEPT_CODES.keys():
        export_json(temp_dept_string, COURSE_DETAILS, COMPLETE_COURSE_GRAPH)
        print(temp_dept_string + ' done')

print(""" That's all folks! """)
#%% temp manual debugging section
#CURRENT_CATALOG_URLS = get_catalog_urls()
#CATALOG_URLS = get_date(CURRENT_CATALOG_URLS)
#COURSE_URLS = get_courses(CATALOG_URLS)
#UNIQUE_RECENT_URLS = get_most_recent_course_urls(COURSE_URLS)
#COURSE_DETAILS = get_course_info(UNIQUE_RECENT_URLS, COURSE_URLS)
#PREREQS = get_prereqs(COURSE_DETAILS)
#test_prereqs(PREREQS, COURSE_DETAILS)
#COMPLETE_COURSE_GRAPH = make_course_graph(COURSE_DETAILS, PREREQS)
#for temp_dept_string in DEPT_CODES.keys():
#    subgraph = make_subgraph(temp_dept_string, COURSE_DETAILS, \
#                               COMPLETE_COURSE_GRAPH)
#    print(temp_dept_string)
#    print(subgraph.ecount())
#    export_json(temp_dept_string, COURSE_DETAILS, COMPLETE_COURSE_GRAPH)
#    print(temp_dept_string + ' done')
