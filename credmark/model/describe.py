from abc import abstractmethod
import inspect
import re
from typing import List, Tuple, Type, Union
from copy import deepcopy

from .base import Model
from credmark.dto import DTO, EmptyInput
from .errors import ModelDataErrorDTO, ModelDefinitionError


class WrongModelMethodSignature(ModelDefinitionError):
    pass


class InvalidModelSlug(ModelDefinitionError):
    pass


DICT_SCHEMA = {"title": "Object", "type": "object", "properties": {}}

# We could probably get the input and output DTOs from
# the run() method signature instead of passing them as params to
# the decorator but there may be reasons why they want to use
# different types and the DTOs are used to document the schema.

MAX_SLUG_LENGTH = 64
model_slug_re = re.compile(r'^(([A-Za-z0-9]+\-)*[A-Za-z0-9]+\.)?([A-Za-z0-9]+\-)*[A-Za-z0-9]+$')


class ModelErrorDesc:
    @abstractmethod
    def schema(self, slug: str):
        pass


class ModelDataErrorDesc(ModelErrorDesc):
    """
    A description of ModelDataErrors raised by a model.

    Contains the list of possible codes and their descriptions.
    """

    def __init__(self, description: str, code: Union[str, None] = None,
                 code_desc: Union[str, None] = None,
                 codes: Union[List[Tuple[str, str]], List[str], None] = None):
        """
        Create a description of a ModelDataError.

        Args:
        description: Description of the error
        code: Error code
        code_desc: Description of error code
        codes: List of tuples `(code, code_description)`
        """
        self.description = description
        self.codes: List[Tuple[str, str]] = []
        if codes is not None:
            for ct in codes:
                self.codes.append(ct if isinstance(ct, tuple) else (ct, ct))
        if code is not None:
            self.codes.append((code, code_desc) if code_desc is not None else (code, code))
        self.codes.sort()
        self.__schema = None

    def schema(self, slug: str):
        if self.__schema is None:
            self.__schema = schema = deepcopy(ModelDataErrorDTO.schema())
            schema['title'] = f'ModelDataError_{slug.replace(".","_").replace("-", "_")}'
            schema['description'] = self.description
            code_prop = schema['properties']['code']
            code_prop['enum'] = [ct[0] for ct in self.codes]
            code_desc_list = [f"\'{ct[0]}\' - {ct[1]}" for ct in self.codes]
            code_prop['description'] = f'Code values: {"; ".join(code_desc_list)}'
            required = schema['required']
            if 'code' not in required:
                required.append('code')
        return self.__schema


def validate_model_slug(slug: str, prefix: Union[str, None] = None):
    if prefix is not None and not slug.startswith(prefix):
        raise InvalidModelSlug(f'Slug for model {slug} must start with "{prefix}"')

    if model_slug_re.match(slug) is None or len(slug) > MAX_SLUG_LENGTH:
        quoted_prefix = f'"{prefix}"' if prefix else ''
        raise InvalidModelSlug(
            f'Invalid model slug "{slug}". '
            f'{"Following the prefix " + quoted_prefix if prefix else "Following a prefix and dot"}, '
            'slugs must start and end with a letter or number and may contain hyphens.')
    if len(slug) > MAX_SLUG_LENGTH:
        raise InvalidModelSlug(
            f'Invalid model slug "{slug}". '
            'Slugs must be not more than {MAX_SLUG_LENGTH} characters.')


def describe(slug: str,   # pylint: disable=locally-disabled, invalid-name
             version: str,
             tags: Union[list[str], None] = None,
             display_name: Union[str, None] = None,
             description: Union[str, None] = None,
             developer: Union[str, None] = None,
             input: Union[Type[DTO], Type[dict]] = EmptyInput,
             output: Union[Type[DTO], Type[dict], None] = None,
             errors: Union[List[ModelErrorDesc], None] = None):
    def wrapper(cls_in):
        def is_parent(child, parent):
            found = parent in child.__bases__
            return found or True in [is_parent(pp, parent) for pp in child.__bases__]

        if not is_parent(cls_in, Model):
            cls = type(cls_in.__name__, (Model, *cls_in.__bases__), dict(cls_in.__dict__))
        else:
            cls = cls_in

        mod_parts = cls.__dict__['__module__'].split('.')
        if len(mod_parts) > 1 and mod_parts[1] == 'contrib':
            validate_model_slug(slug, 'contrib.')
        else:
            validate_model_slug(slug)

        try:
            error_schemas = [] if errors is None or len(
                errors) == 0 else [err_desc.schema(slug) for err_desc in errors]
        except Exception as err:
            raise ModelDefinitionError(
                f'Exception processing "errors" in model {slug} describe(): {err}')

        attr_value = {
            'credmarkModelManifest': 'v1',
            'model': {
                'slug': slug,
                'version': version,
                'tags': tags,
                'display_name': display_name,
                'description': description,
                'developer': developer if developer is not None else '',
                'input': input.schema() if input is not None and issubclass(input, DTO)
                else DICT_SCHEMA,
                'output': output.schema() if output is not None and issubclass(output, DTO)
                else DICT_SCHEMA,
                'errors': error_schemas,
                'class': cls.__dict__['__module__'] + '.' + cls.__name__
            }
        }

        attr_name = '_manifest'

        def get_attr(self, attr_name=attr_name):
            return getattr(self, '_' + attr_name)
        attr_prop = property(get_attr, None)
        setattr(cls, attr_name, attr_prop)
        setattr(cls, '_' + attr_name, attr_value)

        setattr(cls, 'slug', slug)
        setattr(cls, 'version', version)
        setattr(cls, 'inputDTO', input)
        setattr(cls, 'outputDTO', output)

        # Checks for the class
        # 1. it need to be inherited from Model class
        assert is_parent(cls, Model)

        # 2. has abstract functions as defined in the Model class
        method_list = [method for method in dir(Model)
                       if method.startswith('__') is False and
                       '__isabstractmethod__' in Model.__dict__[method].__dict__ and
                       Model.__dict__[method].__isabstractmethod__]

        for method in method_list:
            found_this_method = False
            for mro_cls in cls.__mro__:
                if method not in mro_cls.__dict__:
                    continue

                found_this_method = True

                # Since the run method is overloaded, the signatures won't match exactly.
                # TODO: Add parameter and return value type compatibility check
                break

            if not found_this_method:
                raise WrongModelMethodSignature(
                    f'Model {cls.__name__} misses a method {method}() with signature {inspect.signature(Model.__dict__[method])}')  # pylint: disable=line-too-long

        return cls

    return wrapper
