def calc_mulens_diagnostics(event, pspl_model, fspl_model, straightline_model):
    """
    Function to compare the results of PyLIMA model fits for PSPL and FSPL
    for a single event
    """
    if pspl_model and straightline_model:
        compare_model_goodness_of_fit(event, pspl_model, straightline_model)

    if fspl_model and straightline_model:
        compare_model_goodness_of_fit(event, fspl_model, straightline_model)

def get_best_mulens_model(pspl_model, fspl_model):
    """
    Function returns the microlensing model with the lowest reduced chisq.
    """

    if pspl_model and fspl_model:
        if pspl_model.red_chisq <= fspl_model.red_chisq:
            best_model = pspl_model
        else:
            best_model = fspl_model
    else:
        best_model = None

    return best_model

def calc_flare_diagnostics(event, best_mulens, davenport_model, pitkin_model):
    """
    Function to compare the flare model fits with the best fitting microlensing model
    """

    if best_mulens and davenport_model:
        compare_model_goodness_of_fit(event, best_mulens, davenport_model)

    if best_mulens and pitkin_model:
        compare_model_goodness_of_fit(event, best_mulens, pitkin_model)

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
