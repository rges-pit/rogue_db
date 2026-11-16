from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from custom_code.models import VariableStar
from custom_code import variable_stars
from custom_code.management.commands.ingest_variable_catalog import OGLE_TYPES, UNCLASSIFIED_TYPE
from collections import Counter
import logging

logger = logging.getLogger(__name__)

# The types stars were given before the typed OGLE catalogs, and the type each is now called: those that
# the typed catalogs have a name for, and those they don't, which are given a readable name here. The
# flare type isn't among them, as the code relies on it being called 'flare', and neither is the
# unclassified type, which isn't the same as 'OGLE Variable': the stars of that are known to be of a
# kind that isn't one of the other types.
TYPED_CATALOG_NAMES = {
    'eclipsing_binary': 'Eclipsing binary',
    'lpv': 'Long Period Variable',
    'rrlyrae': 'RR Lyra',
    'delta_scuti': 'Delta Scuti',
    'cepheid': 'Cepheid',
}
READABLE_NAMES = {
    'hb': 'Heartbeat star',
    'dn': 'Dwarf nova',
    'miras': 'Mira variable',
    'cv': 'Cataclysmic variable',
    'CV': 'Cataclysmic variable',
    'Cv': 'Cataclysmic variable',
    'bestar': 'Be star',
}
OLD_TYPES = {**TYPED_CATALOG_NAMES, **READABLE_NAMES}
assert all(name in OGLE_TYPES for name in TYPED_CATALOG_NAMES.values())

# Every name a type is made of in the end, other than free text
KNOWN_TYPES = set(OGLE_TYPES) | set(OLD_TYPES.values()) | {'flare', UNCLASSIFIED_TYPE}

def rewritten_type(star_type):
    """
    A star's type with the old names in it rewritten as the new ones, or None if it hasn't any. Stars
    with more than one type have each of them rewritten, and then they're joined as the typed catalogs
    would have, and so are in alphabetical order. A type that has anything in it that isn't a name
    known here is free text (the MOA catalogs' comments are, and where they have a '/' it means "or"),
    and isn't rewritten.
    """
    names = variable_stars.split(star_type)
    if not any(name in OLD_TYPES for name in names):
        return None
    if not all(name in OLD_TYPES or name in KNOWN_TYPES for name in names):
        return None
    return variable_stars.combine(*[OLD_TYPES.get(name, name) for name in names])

class Command(BaseCommand):
    help = (
        'Tool to rewrite the types of variable stars that were given before the typed OGLE catalogs '
        'as the names those catalogs give them (eclipsing_binary as Eclipsing binary, and so on), and '
        'those they don\'t have a name for as readable ones (hb as Heartbeat star, and so on). '
        'Run it after ingesting the typed catalogs: a star that is typed with the names of those catalogs '
        'is then taken to be in one of them, and has the type of any other it is ingested from added to it.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would be rewritten without doing it')

    def handle(self, *args, **options):

        # There are only a few dozen different types, so the stars are changed a type at a time,
        # in the database, and not one star at a time
        counts = VariableStar.objects.exclude(type=None).values_list('type').annotate(n=Count('pk')).order_by()
        rewrites = {}
        for star_type, n_stars in counts:
            new_type = rewritten_type(star_type)
            if new_type is not None and new_type != star_type:
                rewrites[star_type] = (new_type, n_stars)

        for old_type, (new_type, n_stars) in sorted(rewrites.items(), key=lambda item: -item[1][1]):
            logger.info(str(n_stars) + ' stars: ' + old_type + ' -> ' + new_type)
        logger.info('Rewriting the type of ' + str(sum(n for new, n in rewrites.values())) + ' stars')

        if options['dry_run']:
            logger.info('Dry run: nothing was changed')
        else:
            with transaction.atomic():
                for old_type, (new_type, n_stars) in rewrites.items():
                    VariableStar.objects.filter(type=old_type).update(type=new_type)

        # What there is, after this, that isn't a name known here
        left = Counter()
        for star_type, n_stars in counts:
            final_type = rewrites[star_type][0] if star_type in rewrites else star_type
            if any(name not in KNOWN_TYPES for name in variable_stars.split(final_type)):
                left[final_type] += n_stars
        for star_type, n_stars in left.most_common():
            logger.info('Left as it is, not being a name known here: '
                        + str(n_stars) + ' stars of type ' + repr(star_type))
