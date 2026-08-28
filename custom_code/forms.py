from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div

from .models import RGESAlert


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
