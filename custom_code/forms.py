from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Row, Column, HTML

from .models import (RGESAlert, PSPLModel, FSPLModel, WideBoundPlanetModel,
                     DavenportFlareModel, PitkinFlareModel)


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


class PSPLModelForm(forms.ModelForm):
    """
    Creates/edits a PSPLModel. Includes the fields inherited from
    EventModel (event, model_type, chisq, ...) as well as this type's own
    parameters.
    """

    class Meta:
        model = PSPLModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_type'].initial = PSPLModel.ModelTypes.pspl
        self.fields['model_type'].disabled = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('event', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('chisq', css_class='col-md-3'),
                    Column('BIC', css_class='col-md-3'),
                ),
                HTML('<h5>PSPL Microlensing Parameters</h5>'),
                Row(
                    Column('t0', css_class='col-md-3'),
                    Column('t0_error', css_class='col-md-3'),
                    Column('u0', css_class='col-md-3'),
                    Column('u0_error', css_class='col-md-3'),
                    Column('tE', css_class='col-md-3'),
                    Column('tE_error', css_class='col-md-3'),
                ),
                Row(
                    Column('piEN', css_class='col-md-3'),
                    Column('piEN_error', css_class='col-md-3'),
                    Column('piEE', css_class='col-md-3'),
                    Column('piEE_error', css_class='col-md-3'),
                ),
                css_class='border rounded p-3 mb-3',
            ),
        )

class FSPLModelForm(forms.ModelForm):
    """
    Creates/edits an FSPLModel. Includes the fields inherited from
    EventModel (event, model_type, chisq, rho, ...) as well as this type's own
    parameters.
    """

    class Meta:
        model = FSPLModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_type'].initial = FSPLModel.ModelTypes.fspl
        self.fields['model_type'].disabled = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('event', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('chisq', css_class='col-md-3'),
                    Column('BIC', css_class='col-md-3'),
                ),
                HTML('<h5>FSPL Microlensing Parameters</h5>'),
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
            ),
        )

class WideBoundPlanetModelForm(forms.ModelForm):
    """
    Creates/edits an FSPLModel. Includes the fields inherited from
    EventModel (event, model_type, chisq, rho, ...) as well as this type's own
    parameters.
    """

    class Meta:
        model = WideBoundPlanetModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_type'].initial = WideBoundPlanetModel.ModelTypes.wide_bound_planet
        self.fields['model_type'].disabled = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('event', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('chisq', css_class='col-md-3'),
                    Column('BIC', css_class='col-md-3'),
                ),
                HTML('<h5>Wide Bound Planet Microlensing Parameters</h5>'),
                Row(
                    Column('tc', css_class='col-md-3'),
                    Column('tc_error', css_class='col-md-3'),
                    Column('uc', css_class='col-md-3'),
                    Column('uc_error', css_class='col-md-3'),
                ),
                Row(
                    Column('tE', css_class='col-md-3'),
                    Column('tE_error', css_class='col-md-3'),
                    Column('rho', css_class='col-md-3'),
                    Column('rho_error', css_class='col-md-3'),
                ),
                Row(
                    Column('s', css_class='col-md-3'),
                    Column('s_error', css_class='col-md-3'),
                    Column('q', css_class='col-md-3'),
                    Column('q_error', css_class='col-md-3'),
                    Column('alpha', css_class='col-md-3'),
                    Column('alpha_error', css_class='col-md-3'),
                ),
                css_class='border rounded p-3 mb-3',
            ),
        )

class DavenportFlareModelForm(forms.ModelForm):
    """
    Creates/edits a DavenportFlareModel.
    """

    class Meta:
        model = DavenportFlareModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_type'].initial = DavenportFlareModel.ModelTypes.davenport_flare
        self.fields['model_type'].disabled = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('event', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('chisq', css_class='col-md-3'),
                    Column('BIC', css_class='col-md-3'),
                ),
                HTML('<h5>Flare Parameters</h5>'),
                Row(
                    Column('t_peak', css_class='col-md-4'),
                    Column('t_peak_error', css_class='col-md-4'),
                    Column('peak_amplitude', css_class='col-md-4'),
                    Column('peak_amplitude_error', css_class='col-md-4'),
                ),
                Row(
                    Column('t_FWHM', css_class='col-md-4'),
                    Column('t_FWHM_error', css_class='col-md-4'),
                ),
                css_class='border rounded p-3 mb-3',
            ),
        )

class PitkinFlareModelForm(forms.ModelForm):
    """
    Creates/edits a PitkinFlareModel.
    """

    class Meta:
        model = PitkinFlareModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_type'].initial = PitkinFlareModel.ModelTypes.pitkin_flare
        self.fields['model_type'].disabled = True

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('event', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('chisq', css_class='col-md-3'),
                    Column('BIC', css_class='col-md-3'),
                ),
                HTML('<h5>Flare Parameters</h5>'),
                Row(
                    Column('t_peak', css_class='col-md-4'),
                    Column('t_peak_error', css_class='col-md-4'),
                    Column('peak_amplitude', css_class='col-md-4'),
                    Column('peak_amplitude_error', css_class='col-md-4'),
                ),
                Row(
                    Column('tau_gaussian_rise', css_class='col-md-4'),
                    Column('tau_gaussian_rise_error', css_class='col-md-4'),
                    Column('tau_exponential_decay_rise', css_class='col-md-4'),
                    Column('tau_exponential_decay_rise_error', css_class='col-md-4'),
                ),
                css_class='border rounded p-3 mb-3',
            ),
        )
