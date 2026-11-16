from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, F, Window
from custom_code.models import VariableStar
from custom_code import variable_stars
from itertools import groupby
import logging

logger = logging.getLogger(__name__)

# What the stars of a group have joined together
MERGED_FIELDS = list(variable_stars.VARIABLE_STAR_ID_FIELDS) + ['type']

class Command(BaseCommand):
    help = (
        'Tool to merge the variable stars in the database that are at exactly the same position, as '
        'the same star can be listed in more than one catalog. The earliest added keeps its place, with '
        'the IDs and variable types of them all, joined.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would be merged without merging')

    def handle(self, *args, **options):

        # The stars that share their position with another. The position has to be exactly the same
        # (that is the same star in two catalogs, rather than a neighbour), and the comparison is
        # done by the database as it is stored.
        colocated = VariableStar.objects.annotate(
            n_here=Window(expression=Count('pk'), partition_by=[F('ra'), F('dec')])
        ).filter(n_here__gt=1).order_by('ra', 'dec', 'pk')

        merged_stars = []
        redundant_pks = []
        too_long = 0
        n_groups = 0
        for position, group in groupby(colocated.iterator(), key=lambda star: (star.ra, star.dec)):
            n_groups += 1
            stars = list(group)
            keeper, others = stars[0], stars[1:]

            # Each field joins the values of all the stars
            values = {field: variable_stars.combine(*[getattr(star, field) for star in stars])
                      for field in MERGED_FIELDS}

            # A value that doesn't fit in the field means this isn't merged, and is left for a person to look at
            if any(value and len(value) > VariableStar._meta.get_field(field).max_length
                   for field, value in values.items()):
                too_long += 1
                logger.warning('Not merging the ' + str(len(stars)) + ' stars at ' + repr(position)
                               + ', whose joined values would be too long: ' + repr(values))
                continue

            for field, value in values.items():
                setattr(keeper, field, value)
            merged_stars.append(keeper)
            redundant_pks.extend(star.pk for star in others)
            logger.debug('Merging ' + repr([star.pk for star in stars]) + ' at ' + repr(position)
                         + ' as ' + repr(values))

        logger.info('Found ' + str(n_groups) + ' positions with more than one star: merging '
                    + str(len(merged_stars)) + ' of them, removing ' + str(len(redundant_pks))
                    + ' stars that are listed in them again' + (', ' + str(too_long) + ' not merged' if too_long else ''))
        if options['dry_run']:
            logger.info('Dry run: nothing was changed')
            return

        with transaction.atomic():
            for start in range(0, len(redundant_pks), 5000):
                VariableStar.objects.filter(pk__in=redundant_pks[start:start + 5000]).delete()
            VariableStar.objects.bulk_update(merged_stars, MERGED_FIELDS, batch_size=1000)
