
def compare_model_goodness_of_fit(event, model1, model2):
    """
    Function to compare the goodness-of-fit parameters for the two models given.
    The models are order so that the straight line model is always second
    """

    # Calculate the difference between the chi2 values and the BIC
    delta_chisq = model1.chisq - model2.chisq
    delta_bic = model1.BIC - model2.BIC

    # If model2 is a

    # Store these parameters on the Event
    if model1.model_type == 'PSPL microlensing' and model2.model_type == 'Straight line':
        event.delta_chi2_PSPL = delta_chisq
        event.delta_BIC_PSPL = delta_bic
        event.save()
    elif model1.model_type == 'FSPL microlensing' and model2.model_type == 'Straight line':
        event.delta_chi2_FSPL = delta_chisq
        event.delta_BIC_FSPL = delta_bic
        event.save()
    elif model1.model_type == 'PSPL microlensing' and model2.model_type == 'Davenport flare':
        event.delta_chi2_PSPL_bestflare = delta_chisq
        event.delta_BIC_PSPL_bestflare = delta_bic
        event.save()
    elif model1.model_type == 'FSPL microlensing' and model2.model_type == 'Davenport flare':
        event.delta_chi2_FSPL_bestflare = delta_chisq
        event.delta_BIC_FSPL_bestflare = delta_bic
        event.save()

def compare_flare_models(event, mulens_model, davenport_model, pitkin_model):
    """
    Function to compare the results of fitting different flare models to this event,
    and to calculate the diagnostics comparing the flare models with microlensing models

    Parameters:
        event               Event object
        mulens_model        EventModel for microlensing
        davenport_model   EventModel results of Davenport model fit
        pitkin_model      EventModel        results of Pitkin model fit
    """

    if davenport_model.chisq <= pitkin_model.chisq:
        best_flare = davenport_model
    else:
        best_flare = pitkin_model

    delta_chisq = mulens_model.chisq - best_flare.chisq
    delta_bic = mulens_model.BIC - best_flare.BIC

    if mulens_model.model_type == 'PSPL microlensing':
        event.delta_chi2_PSPL_bestflare = delta_chisq
        event.delta_BIC_PSPL_bestflare = delta_bic
        event.save()
    elif mulens_model.model_type == 'FSPL microlensing':
        event.delta_chi2_FSPL_bestflare = delta_chisq
        event.delta_BIC_FSPL_bestflare = delta_bic
        event.save()
