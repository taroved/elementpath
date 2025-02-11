#
# Copyright (c), 2018-2021, SISSA (International School for Advanced Studies).
# All rights reserved.
# This file is distributed under the terms of the MIT License.
# See the file 'LICENSE' in the root directory of the present
# distribution, or http://opensource.org/licenses/MIT.
#
# @author Davide Brunato <brunato@sissa.it>
#
from abc import ABCMeta, abstractmethod
from functools import lru_cache, cached_property
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Union

from elementpath._typing import Iterator
from elementpath.exceptions import ElementPathTypeError
from elementpath.protocols import XsdTypeProtocol, XsdAttributeProtocol, \
    XsdElementProtocol, XsdSchemaProtocol
from elementpath.namespaces import XSD_ANY_SIMPLE_TYPE, XSD_ANY_TYPE
from elementpath.datatypes import AtomicType
from elementpath.etree import is_etree_element
from elementpath.xpath_context import XPathSchemaContext

if TYPE_CHECKING:
    from elementpath.xpath_tokens import XPath2ParserType

PathResult = Union[XsdSchemaProtocol, XsdElementProtocol, XsdAttributeProtocol]


class AbstractSchemaProxy(metaclass=ABCMeta):
    """
    Abstract base class for defining schema proxies. An implementation can override
    initialization type annotations

    :param schema: a schema instance compatible with the XsdSchemaProtocol.
    :param base_element: the schema element used as base item for static analysis.
    """

    def __init__(self, schema: XsdSchemaProtocol,
                 base_element: Optional[XsdElementProtocol] = None) -> None:
        if not is_etree_element(schema):
            raise ElementPathTypeError(
                "argument {!r} is not a compatible schema instance".format(schema)
            )
        if base_element is not None and not is_etree_element(base_element):
            raise ElementPathTypeError(
                "argument 'base_element' is not a compatible element instance"
            )

        self._schema = schema
        self._base_element: Optional[XsdElementProtocol] = base_element

    def bind_parser(self, parser: 'XPath2ParserType') -> None:
        """
        Binds a parser instance with schema proxy adding the schema's atomic types constructors.
        This method can be redefined in a concrete proxy to optimize schema bindings.

        :param parser: a parser instance.
        """
        if parser.schema is not self:
            parser.schema = self

        for xsd_type in self.iter_atomic_types():
            if xsd_type.name is not None:  # pragma: no cover
                parser.schema_constructor(xsd_type.name)

    def get_context(self) -> XPathSchemaContext:
        """
        Get a context instance for static analysis phase.

        :returns: an `XPathSchemaContext` instance.
        """
        return XPathSchemaContext(root=self._schema, item=self._base_element)

    def find(self, path: str, namespaces: Optional[Dict[str, str]] = None) \
            -> Optional[PathResult]:
        """
        Find a schema element or attribute using an XPath expression.

        :param path: an XPath expression that selects an element or an attribute node.
        :param namespaces: an optional mapping from namespace prefix to namespace URI.
        :return: The first matching schema component, or ``None`` if there is no match.
        """
        @lru_cache(maxsize=None)
        def cached_find(path_: str) -> Optional[PathResult]:
            return self._schema.find(path_)

        if not namespaces:
            return cached_find(path)
        return self._schema.find(path, namespaces)

    @property
    def xsd_version(self) -> str:
        """The XSD version, returns '1.0' or '1.1'."""
        return self._schema.xsd_version

    @cached_property
    def validity(self) -> Optional[str]:
        return getattr(self._schema, 'validity', None)

    @cached_property
    def validation_attempted(self) -> Optional[str]:
        return getattr(self._schema, 'validation_attempted', None)

    def get_type(self, qname: str) -> Optional[XsdTypeProtocol]:
        """
        Get the XSD global type from the schema's scope. A concrete implementation must
        return an object that supports the protocols `XsdTypeProtocol`, or `None` if
        the global type is not found.

        :param qname: the fully qualified name of the type to retrieve.
        :returns: an object that represents an XSD type or `None`.
        """
        xsd_type = self._schema.maps.types.get(qname)
        if isinstance(xsd_type, tuple):
            return None
        return xsd_type

    def get_attribute_node_type(self, path: str, name: Optional[str]) \
            -> Optional[XsdTypeProtocol]:

        validity = self.validity
        validation_attempted = self.validation_attempted
        if validity is None or validation_attempted is None:
            return None
        elif validity != 'valid' or validation_attempted != 'full':
            return self.get_type(XSD_ANY_SIMPLE_TYPE)

        xsd_attribute = self.find(path)
        if xsd_attribute is None:
            return None

        try:
            xsd_type = xsd_attribute.type  # type: ignore[union-attr]
        except AttributeError:
            raise ElementPathTypeError(f"found a non XSD attribute {xsd_attribute}")
        else:
            if xsd_type is None and name is not None:
                xsd_attribute = self.get_attribute(name)
                if xsd_attribute is not None:
                    return xsd_attribute.type
            return xsd_type

    def get_element_node_type(self, path: str, name: Optional[str]) \
            -> Optional[XsdTypeProtocol]:
        validity = self.validity
        validation_attempted = self.validation_attempted
        if validity is None or validation_attempted is None:
            return None
        elif validity != 'valid' or validation_attempted != 'full':
            return self.get_type(XSD_ANY_TYPE)

        xsd_element = self.find(path)
        if xsd_element is None:
            return None

        try:
            xsd_type = xsd_element.type  # type: ignore[union-attr]
        except AttributeError:
            raise ElementPathTypeError(f"found a non XSD element {xsd_element}")
        else:
            if xsd_type is None and name is not None:
                xsd_element = self.get_element(name)
                if xsd_element is not None:
                    return xsd_element.type
            return xsd_type

    def get_attribute(self, qname: str) -> Optional[XsdAttributeProtocol]:
        """
        Get the XSD global attribute from the schema's scope. A concrete implementation must
        return an object that supports the protocol `XsdAttributeProtocol`, or `None` if
        the global attribute is not found.

        :param qname: the fully qualified name of the attribute to retrieve.
        :returns: an object that represents an XSD attribute or `None`.
        """
        xsd_attribute = self._schema.maps.attributes.get(qname)
        if isinstance(xsd_attribute, tuple):
            return None
        return xsd_attribute

    def get_element(self, qname: str) -> Optional[XsdElementProtocol]:
        """
        Get the XSD global element from the schema's scope. A concrete implementation must
        return an object that supports the protocol `XsdElementProtocol` interface, or
        `None` if the global element is not found.

        :param qname: the fully qualified name of the element to retrieve.
        :returns: an object that represents an XSD element or `None`.
        """
        xsd_element = self._schema.maps.elements.get(qname)
        if isinstance(xsd_element, tuple):
            return None
        return xsd_element

    def get_substitution_group(self, qname: str) -> Optional[Set[XsdElementProtocol]]:
        """
        Get a substitution group. A concrete implementation must returns a list containing
        substitution elements or `None` if the substitution group is not found. Moreover each item
        of the returned list must be an object that implements the `AbstractXsdElement` interface.

        :param qname: the fully qualified name of the substitution group to retrieve.
        :returns: a list containing substitution elements or `None`.
        """
        return self._schema.maps.substitution_groups.get(qname)

    @abstractmethod
    def is_instance(self, obj: Any, type_qname: str) -> bool:
        """
        Returns `True` if *obj* is an instance of the XSD global type, `False` if not.

        :param obj: the instance to be tested.
        :param type_qname: the fully qualified name of the type used to test the instance.
        """

    @abstractmethod
    def cast_as(self, obj: Any, type_qname: str) -> AtomicType:
        """
        Converts *obj* to the Python type associated with an XSD global type. A concrete
        implementation must raises a `ValueError` or `TypeError` in case of a decoding
        error or a `KeyError` if the type is not bound to the schema's scope.

        :param obj: the instance to be cast.
        :param type_qname: the fully qualified name of the type used to convert the instance.
        """

    @abstractmethod
    def iter_atomic_types(self) -> Iterator[XsdTypeProtocol]:
        """
        Returns an iterator for not builtin atomic types defined in the schema's scope. A concrete
        implementation must yield objects that implement the protocol `XsdTypeProtocol`.
        """


__all__ = ['AbstractSchemaProxy']
