from models import Country, Region, City

country_words = frozenset(['new', 'north', 'south', 'united'])
region_words = frozenset(['south', 'north', 'east', 'west', 'new'])
city_words = frozenset(['south', 'north', 'east', 'west', 'santa', 'upper', 'lower', 'fort', 'cape',
						'city', 'town', 'beach', 'square', 'centre', 'hill', 'park', 'point',
						'hollow', 'harbor', 'shore', 'head', 'cove', 'station', 'height',
						'fall', 'bay', 'river', 'island', 'grove', 'valley', 'lake', 'creek',
						'cloud', 'rapid', 'spring', 'arrow', 'township', 'village', 'grand', 'palm',
						'point', 'port', 'prince', 'king', 'queen'
						])

def __parse_country(tokens):
	# consume all country_words and one word that doesn't fit in country_words
	uniqueFound = False
	consumed = 0
	for i in range(len(tokens)):
		token = tokens[-i].lower()
		if token in country_words:
			consumed += 1
			continue
		elif not uniqueFound:
			consumed += 1
			uniqueFound = True
			continue
		else:
			break
	return consumed

def __parse_region(tokens):
	# consume all region_words and one word that doesn't fit in region_words
	uniqueFound = False
	consumed = 0
	for i in range(len(tokens)):
		token = tokens[-i].lower()
		if token in region_words:
			consumed += 1
			continue
		elif not uniqueFound:
			consumed += 1
			uniqueFound = True
			continue
		else:
			break
	return consumed

def __parse_city(tokens):
	# consume all city_words, any words that are 3 letters or less and one word that doesn't fit either of those categories
	# (all 3 letters or less assumed to go with a city name) la, des, san, los, old, new, mt, st, eau
	uniqueFound = False
	consumed = 0
	for i in range(len(tokens)):
		token = tokens[-i]
		if len(token) <= 3:
			consumed += 1
			continue
		else:
			token = token.lower()
			if token.rstrip('s') in city_words:
				consumed += 1
				continue
			elif not uniqueFound:
				consumed += 1
				uniqueFound = True
				continue
			else:
				break
	return consumed
	

def resolve_query_place(query):
	""" Convert a query into a place, as (the remaining search query, queryset of places). """

	allTokens = [token for token in query.replace(',', ' ').split(' ') if token]
	if not len(allTokens):
		return ('', None)
	components = [component.split(' ') for component in query.split(',') if component]
	cities = None
	regions = None
	countries = None
	places = None
	consumed = 0
	
	def get_component():
		""" Returns a sub sequence of a component. This makes use of the commas as hard delimiters to separate city, state, etc. """
		componentConsumed = consumed
		for i in range(len(components)):
			if componentConsumed < len(components[-i]):
				return components[-i][:-componentConsumed if componentConsumed else None]
			else:
				componentConsumed -= len(components[-i])
		return []

	if len(allTokens[-1]) == 2 and allTokens[-1].isalpha():
		if len(allTokens) >= 2 and len(allTokens[-2]) == 2 and allTokens[-2].isalpha():
			# A county and region code were given. e.g. CA US -> US.CA
			regions = Region.objects.filter(code='%s.%s' % (allTokens[-1].upper(), allTokens[-2].upper()))
			consumed = 2
		else:
			# A single region or country code was given
			regions = Region.objects.filter(code__endswith=allTokens[-1].upper())
			if not len(regions):
				countries = Country.objects.filter(code=allTokens[-1].upper()).order_by('-population')
			consumed = 1
		if len(regions):
			# Found a region, also try to find the city that goes with the region
			places = regions
			cityConsumed = __parse_city(get_component())
			if cityConsumed:
				cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None]), region__in=regions).order_by('-population')
				if len(cities):
					places = cities
					consumed += cityConsumed
		elif len(countries):
			# Found a country, also try to find the city that goes with the country
			places = countries
			cityConsumed = __parse_city(get_component())
			if cityConsumed:
				cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None]), country=countries[0]).order_by('-population')
				if len(cities):
					places = cities
					consumed += cityConsumed
	else:
		# No codes were given, the query is more free form
		# Match the country first
		countryConsumed = __parse_country(get_component())
		if countryConsumed:
			countries = Country.objects.filter(name__iexact=' '.join(allTokens[-(consumed + countryConsumed):-consumed if consumed else None])).order_by('-population')
			if len(countries):
				places = countries
				consumed += countryConsumed
		# Try region then city matching
		regionConsumed = __parse_region(get_component())
		if regionConsumed:
			if countries and len(countries):
				regions = Region.objects.filter(name__iexact=' '.join(allTokens[-(consumed + regionConsumed):-consumed if consumed else None]), country=countries[0])
			else:
				regions = Region.objects.filter(name__iexact=' '.join(allTokens[-(consumed + countryConsumed):-consumed if consumed else None]))
			if len(regions):
				places = regions
				consumed += regionConsumed
		cityConsumed = __parse_city(get_component())
		if cityConsumed:
			if regions and len(regions):
				cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None]), region__in=regions).order_by('-population')
			elif len(countries):
				cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None]), country=countries[0]).order_by('-population')
			else:
				cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None])).order_by('-population')
			if len(cities):
				places = cities
				consumed += cityConsumed
		# If region was found without a city go back to just try to resolve it to a city instead
		if (regions and len(regions)) and (not cities or not len(cities)):
			consumed -= regionConsumed
			cityConsumed = __parse_city(get_component())
			if cityConsumed:
				if len(countries):
					cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None]), country=countries[0]).order_by('-population')
				else:
					cities = City.objects.filter(name__iexact=' '.join(allTokens[-(consumed + cityConsumed):-consumed if consumed else None])).order_by('-population')
				if len(cities):
					places = cities
					consumed += cityConsumed
			if not cities or not len(cities):
				# No city found, region is the best match
				consumed -= regionConsumed

	return (' '.join(allTokens[:-consumed if consumed else None]), places)
