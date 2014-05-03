from django.utils.encoding import force_unicode
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point
from django.template.defaultfilters import slugify
from conf import settings
from util import create_model, un_camel

__all__ = [
        'Point', 'Country', 'Region', 'Subregion',
        'City', 'District', 'PostalCode', 'geo_alt_names', 
]

class Place(models.Model):
    name = models.CharField(max_length=200, db_index=True, verbose_name="ascii name")
    slug = models.CharField(max_length=200)

    objects = models.GeoManager()

    class Meta:
        abstract = True

    @property
    def hierarchy(self):
        """Get hierarchy, root first"""
        list = self.parent.hierarchy if self.parent else []
        list.append(self)
        return list

    #def get_absolute_url(self):
    #    return "/".join([place.slug for place in self.hierarchy])

class Country(Place):
    code = models.CharField(max_length=2, db_index=True)
    population = models.IntegerField()
    continent = models.CharField(max_length=2)
    tld = models.CharField(max_length=5)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "countries"

    class API:
        exclude_fields = ('tld',)

    @property
    def parent(self):
        return None
        
    def get_absolute_url(self):
        return '/%s' % slugify(self.code)

    def __unicode__(self):
        return force_unicode(self.name)

class RegionBase(Place):
    name_std = models.CharField(max_length=200, db_index=True, verbose_name="standard name")
    code = models.CharField(max_length=200, db_index=True)
    country = models.ForeignKey(Country)

    levels = ['region', 'subregion']

    class Meta:
        abstract = True

    def __unicode__(self):
        return u'{}, {}'.format(force_unicode(self.name_std), self.parent)

class Region(RegionBase):

    class API:
        exclude_fields = ('country',)

    @property
    def parent(self):
        return self.country
        
    def get_absolute_url(self):
        return '/%s/%s' % (slugify(self.country.code), slugify(self.name))

class Subregion(RegionBase):
    region = models.ForeignKey(Region)

    @property
    def parent(self):
        return self.region

class CityBase(Place):
    name_std = models.CharField(max_length=200, db_index=True, verbose_name="standard name")
    location = models.PointField()
    population = models.IntegerField()

    class Meta:
        abstract = True 

    def __unicode__(self):
        return u'{}, {}'.format(force_unicode(self.name_std), self.parent)

    @property
    def latitude(self):
        return self.location.y

    @property
    def longitude(self):
        return self.location.x

class CityManager(models.GeoManager):
    def nearest_to(self, x, y, count = 0):
        p = Point(float(x), float(y))
        return self.nearest_to_point(p, count)

    def nearest_to_point(self, point, count = 0):
        if count > 0:
            return self.distance(point).order_by('distance')[:count]
        return self.distance(point).order_by('distance')[0]

class City(CityBase):
    region = models.ForeignKey(Region, null=True, blank=True)
    subregion = models.ForeignKey(Subregion, null=True, blank=True)
    country = models.ForeignKey(Country)

    objects = CityManager()

    class Meta:
        verbose_name_plural = "cities"

    class API:
        exclude_fields = ("location", )
        include_related = ("region", "country")
        include_attributes = ("latitude", "longitude")
        list_attributes = ("latitude", "longitude")

    @property
    def parent(self):
        return self.region
    
    def get_absolute_url(self):
        if self.region:
            return '/%s/%s/%s' % (slugify(self.country.code), slugify(self.region.name), slugify(self.name))
        else:
            return '/%s/%s' % (slugify(self.country.code), slugify(self.name))
    
    def nearest_district_to(self, x, y):
        p = Point(float(x), float(y))
        return self.nearest_district_to_point(p)

    def nearest_district_to_point(self, point):
        return self.district_set.distance(point).order_by('distance')[0]

class District(CityBase):
    city = models.ForeignKey(City)

    @property
    def parent(self):
        return self.city

class GeoAltNameManager(models.GeoManager):
    def get_preferred(self, default=None, **kwargs):
        """
        If multiple names are available, get the preferred, otherwise return any existing or the default.
        Extra keywords can be provided to further filter the names.
        """
        try: return self.get(is_preferred=True, **kwargs)
        except self.model.DoesNotExist:
            try: return self.filter(**kwargs)[0]
            except IndexError: return default

def create_geo_alt_names(geo_type):
    geo_alt_names = {}
    for locale in settings.locales:
        name_format = geo_type.__name__ + '{}' + locale.capitalize()
        name = name_format.format('AltName')
        geo_alt_names[locale] = create_model(
            name = name,
            fields = {
                'geo': models.ForeignKey(geo_type,                              # Related geo type
                    related_name = 'alt_names_' + locale),
                'name': models.CharField(max_length=200, db_index=True),        # Alternate name
                'is_preferred': models.BooleanField(),                          # True if this alternate name is an official / preferred name
                'is_short': models.BooleanField(),                              # True if this is a short name like 'California' for 'State of California'
                'objects': GeoAltNameManager(),
                '__unicode__': lambda self: force_unicode(self.name),
            },
            app_label = 'cities',
            module = 'cities.models',
            options = {
                'db_table': 'cities_' + un_camel(name),
                'verbose_name': un_camel(name).replace('_', ' '),
                'verbose_name_plural': un_camel(name_format.format('AltNames')).replace('_', ' '),
            },
        )
    return geo_alt_names

geo_alt_names = {}
for type in [Country, Region, Subregion, City, District]:
    geo_alt_names[type] = create_geo_alt_names(type)

class PostalCode(Place):
    code = models.CharField(max_length=20, primary_key=True)
    location = models.PointField()

    country = models.ForeignKey(Country, related_name = 'postal_codes')
    region = models.ForeignKey(Region, null=True, blank=True, related_name = 'postal_codes')
    subregion = models.ForeignKey(Subregion, null=True, blank=True, related_name = 'postal_codes')

    objects = models.GeoManager()

    class Meta:
        unique_together = [('code', 'country')]

    @property
    def parent(self):
        for parent_name in reversed(['country'] + RegionBase.levels):
            parent_obj = getattr(self, parent_name)
            if parent_obj: return parent_obj
        return None

    @property
    def name_full(self):
        """Get full name including hierarchy"""
        return u', '.join(reversed(self.names)) 
    @property
    def names(self):
        """Get a hierarchy of non-null names, root first"""
        return [e for e in [
            force_unicode(self.country),
            force_unicode(self.region_name),
            force_unicode(self.subregion_name),
            force_unicode(self.district_name),
            force_unicode(self.name),
        ] if e]

    @property
    def latitude(self):
        return self.location.y

    @property
    def longitude(self):
        return self.location.x

    def __unicode__(self):
        return force_unicode(self.code)
