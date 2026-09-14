
def compare_model_goodness_of_fit(event, model1, model2):
    """
    Function to compare the goodness-of-fit parameters for the two models given.
    The models are order so that the straight line model is always second
    """

    # Calculate the difference between the chi2 values and the BIC
    delta_chisq = model1.chisq - model2.chisq
    delta_bic = model1.BIC - model2.BIC

    # Store these parameters on the Event
    if model1.model_type == 'PSPL microlensing' and model2.model_type == 'Straight line':
        event.delta_chi2_PSPL = delta_chisq
        event.delta_BIC_PSPL = delta_bic
        event.save()
    elif model1.model_type == 'FSPL microlensing' and model2.model_type == 'Straight line':
        event.delta_chi2_FSPL = delta_chisq
        event.delta_BIC_FSPL = delta_bic
        event.save()

