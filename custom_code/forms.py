from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Row, Column, Field, HTML

from .models import RGESAlert, TargetModel


class RGESAlertForm(forms.ModelForm):

    class Meta:
        model = RGESAlert
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Crispy forms - the surrounding <form> tag is provided by the template
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        layout_fields = [Div(field_name, css_class="col-md-6") for field_name in self.fields]
        self.helper.layout = Layout(Div(*layout_fields, css_class="row"))

class TargetModelForm(forms.ModelForm):

    class Meta:
        model = TargetModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Crispy forms - the surrounding <form> tag is provided by the template.
        # The template puts an Alpine.js `modelType` variable in scope (x-data) on
        # that <form>, bound below to the model_type field via x-model. The
        # Microlensing/Flare parameter panels use x-show against that variable so
        # only the parameters relevant to the selected model type are shown.
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('target', css_class='col-md-6'),
                Column(Field('model_type', **{'x-model': 'modelType'}), css_class='col-md-6'),
            ),
            Div(
                HTML('<h5>Microlensing Parameters</h5>'),
                Row(
                    Column('t0', css_class='col-md-3'),
                    Column('t0_error', css_class='col-md-3'),
                    Column('u0', css_class='col-md-3'),
                    Column('u0_error', css_class='col-md-3'),
                ),
                Row(
                    Column('tE', css_class='col-md-3'),
                    Column('tE_error', css_class='col-md-3'),
                    Column('rho', css_class='col-md-3'),
                    Column('rho_error', css_class='col-md-3'),
                ),
                Row(
                    Column('piEN', css_class='col-md-3'),
                    Column('piEN_error', css_class='col-md-3'),
                    Column('piEE', css_class='col-md-3'),
                    Column('piEE_error', css_class='col-md-3'),
                ),
                css_class='border rounded p-3 mb-3',
                **{'x-show': "modelType == 'Microlensing'", 'x-transition': ''},
            ),
            Div(
                HTML('<h5>Flare Parameters</h5>'),
                Row(
                    Column('peak_amplitude', css_class='col-md-4'),
                    Column('rise_time', css_class='col-md-4'),
                    Column('equivalent_duration', css_class='col-md-4'),
                ),
                Row(
                    Column('tau1', css_class='col-md-4'),
                    Column('tau2', css_class='col-md-4'),
                ),
                css_class='border rounded p-3 mb-3',
                **{'x-show': "modelType == 'Flare'", 'x-transition': ''},
            ),
        )
