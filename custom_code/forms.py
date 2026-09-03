from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Row, Column, HTML

from .models import RGESAlert, MicrolensingModel, FlareModel


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


class MicrolensingModelForm(forms.ModelForm):
    """
    Creates/edits a MicrolensingModel. Includes the fields inherited from
    EventModel (target, model_type, chisq) as well as this type's own
    parameters -- unlike the old single-table TargetModelForm, there's no
    model-type dropdown here, since a MicrolensingModel *is* a microlensing
    model by construction.
    """

    class Meta:
        model = MicrolensingModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This form always creates a MicrolensingModel, so default model_type
        # to match rather than leaving it on the model's generic 'Unknown'
        # default -- model_type stays editable in case it's ever deliberately
        # reclassified, but shouldn't require the user to remember to set it.
        self.fields['model_type'].initial = MicrolensingModel.ModelTypes.microlensing

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('target', css_class='col-md-6'),
                Column('model_type', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('model_category', css_class='col-md-3'),
                    Column('chisq', css_class='col-md-3'),
                ),
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
            ),
        )


class FlareModelForm(forms.ModelForm):
    """
    Creates/edits a FlareModel. FlareModel has no model_category field (that's
    Microlensing-specific), so this form's shared row is just target/model_type.
    """

    class Meta:
        model = FlareModel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_type'].initial = FlareModel.ModelTypes.flare

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column('target', css_class='col-md-6'),
                Column('model_type', css_class='col-md-6'),
            ),
            Div(
                Row(
                    Column('chisq', css_class='col-md-3'),
                ),
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
            ),
        )
