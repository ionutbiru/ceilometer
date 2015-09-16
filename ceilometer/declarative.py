#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


from jsonpath_rw_ext import parser
import six

from ceilometer.i18n import _


class DefinitionException(Exception):
    def __init__(self, message, definition_cfg):
        super(DefinitionException, self).__init__(message)
        self.definition_cfg = definition_cfg


class Definition(object):
    JSONPATH_RW_PARSER = parser.ExtentedJsonPathParser()

    def __init__(self, name, cfg, plugin_manager):
        self.cfg = cfg
        self.name = name
        self.plugin = None
        if isinstance(cfg, dict):
            if 'fields' not in cfg:
                raise DefinitionException(
                    _("The field 'fields' is required for %s") % name,
                    self.cfg)

            if 'plugin' in cfg:
                plugin_cfg = cfg['plugin']
                if isinstance(plugin_cfg, six.string_types):
                    plugin_name = plugin_cfg
                    plugin_params = {}
                else:
                    try:
                        plugin_name = plugin_cfg['name']
                    except KeyError:
                        raise DefinitionException(
                            _('Plugin specified, but no plugin name supplied '
                              'for %s') % name, self.cfg)
                    plugin_params = plugin_cfg.get('parameters')
                    if plugin_params is None:
                        plugin_params = {}
                try:
                    plugin_ext = plugin_manager[plugin_name]
                except KeyError:
                    raise DefinitionException(
                        _('No plugin named %(plugin)s available for '
                          '%(name)s') % dict(
                              plugin=plugin_name,
                              name=name), self.cfg)
                plugin_class = plugin_ext.plugin
                self.plugin = plugin_class(**plugin_params)

            fields = cfg['fields']
        else:
            # Simple definition "foobar: jsonpath"
            fields = cfg

        if isinstance(fields, list):
            # NOTE(mdragon): if not a string, we assume a list.
            if len(fields) == 1:
                fields = fields[0]
            else:
                fields = '|'.join('(%s)' % path for path in fields)

        if isinstance(fields, six.integer_types):
            self.getter = fields
        else:
            try:
                self.getter = self.JSONPATH_RW_PARSER.parse(fields).find
            except Exception as e:
                raise DefinitionException(
                    _("Parse error in JSONPath specification "
                      "'%(jsonpath)s' for %(name)s: %(err)s")
                    % dict(jsonpath=fields, name=name, err=e), self.cfg)

    def _get_path(self, match):
        if match.context is not None:
            for path_element in self._get_path(match.context):
                yield path_element
            yield str(match.path)

    def parse(self, obj, return_all_values=False):
        if callable(self.getter):
            values = self.getter(obj)
        else:
            return self.getter

        values = [match for match in values
                  if return_all_values or match.value is not None]

        if self.plugin is not None:
            if return_all_values and not self.plugin.support_return_all_values:
                raise DefinitionException("Plugin %s don't allows to "
                                          "return multiple values" %
                                          self.cfg["plugin"]["name"])
            values_map = [('.'.join(self._get_path(match)), match.value) for
                          match in values]
            values = [v for v in self.plugin.trait_values(values_map)
                      if v is not None]
        else:
            values = [match.value for match in values if match is not None]
        if return_all_values:
            return values
        else:
            return values[0] if values else None
