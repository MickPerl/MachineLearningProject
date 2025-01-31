#!/usr/bin/python3
# -*- coding: utf-8 -*-
import re
import sys

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras.layers.experimental.preprocessing import IntegerLookup
from tensorflow.keras.layers.experimental.preprocessing import Normalization
from tensorflow.keras.layers.experimental.preprocessing import StringLookup
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.python.keras.callbacks import ModelCheckpoint
from imblearn.over_sampling import SMOTENC

import save_plots
import config as cfg
from mapping_domande_ambiti_processi import MAPPING_DOMANDE_AMBITI_PROCESSI
from column_converters import COLUMN_CONVERTERS

print("Deep learning model for predicting school dropout (with data from INVALSI)\n")

print("Configuration")
if cfg.check_config() > 0:
    sys.exit(1)

cfg.print_config()

"""
Impostazioni di esecuzione dello script
"""
PRE_ML = False  # Esegue la parte di analisi ed elaborazione del dataset precedente quella di ML.
SAVE_CLEANED_DATASET = False  # Salva il dataset ripulito dalle colonne non utili.
CONVERT_DOMANDE_TO_AMBITI_PROCESSI = False  # Esegue la rimozione delle colonne con domande e le sostituisce con quelle di ambito e processo.

"""
Import del dataset originale
"""
if PRE_ML:
    original_dataset = pd.read_csv(cfg.ORIGINAL_DATASET, sep=';', converters=COLUMN_CONVERTERS)

"""
Cerchiamo colonne che abbiamo percentuali di valori nulli.
"""
if PRE_ML:
    print("Columns with high null values percentages:")
    for col in original_dataset.columns:
        null_values_mean = original_dataset[col].isnull().mean()
        if null_values_mean > 0:
            print(col, '\t\tType: ', original_dataset[col].dtypes, '\tMissing values:',
                  original_dataset[col].isnull().mean().round(3))

columns_high_ratio_null_values = ["codice_orario", "PesoClasse", "PesoScuola", "PesoTotale_Matematica"]
columns_low_ratio_null_values = [
    "voto_scritto_ita",  # 0.683
    "voto_scritto_mat",  # 0.113
    "voto_orale_ita",  # 0.683
    "voto_orale_mat"  # 0.114
]

"""
Cerchiamo colonne con valori univoci o quasi (ad esempio identificativi).
Se ce ne sono, meglio toglierle perché sono inutili.
"""
if PRE_ML:
    dataset_len = len(original_dataset)
    print("Columns with unique values:")
    for col in original_dataset.columns:
        unique_vals = original_dataset[col].nunique()
        if unique_vals / dataset_len > 0.1:
            print(col, "ratio = ", round(unique_vals / dataset_len, 3))
columns_with_unique_values = ["Unnamed: 0", "CODICE_STUDENTE"]

"""
Cerchiamo colonne con sempre lo stesso valore perché non danno informazioni.
Se ce ne sono, meglio toglierle perché sono inutili.
"""
if PRE_ML:
    print("Columns with just one value:")
    for col in original_dataset.columns:
        unique_vals = original_dataset[col].nunique()
        if unique_vals == 1:
            print(col)

columns_with_just_one_value = ["macrotipologia", "livello"]

"""
Rimozione delle colonne indicate in:
- columns_high_ratio_null_values
- columns_low_ratio_null_values (per ora vengono tenute poiché forse possono essere utili)
- columns_with_unique_values
- columns_with_just_one_value
"""
if PRE_ML:
    cleaned_original_dataset: pd.DataFrame = original_dataset.drop(
        columns_high_ratio_null_values + columns_with_unique_values + columns_with_just_one_value, axis=1)

    if SAVE_CLEANED_DATASET:
        cleaned_original_dataset.to_csv(cfg.CLEANED_DATASET, index=False)
    else:
        cleaned_original_dataset = pd.read_csv(cfg.CLEANED_DATASET)

    if "Unnamed: 0" in cleaned_original_dataset.columns:
        cleaned_original_dataset.drop("cleaned_original_dataset", axis=1, inplace=True)

"""
Mapping domande -> (ambiti, processi)
Tutte le colonne delle domande vengono sostituite da colonne ambiti e processi.
"""

list_ambiti_processi = [AP for val in MAPPING_DOMANDE_AMBITI_PROCESSI.values() for AP in val]
ambiti_processi = set(list_ambiti_processi)
conteggio_ambiti_processi = {AP: list_ambiti_processi.count(AP) for AP in ambiti_processi}

if PRE_ML:
    dataset_with_ambiti_processi = cleaned_original_dataset.copy()
    for AP in ambiti_processi:
        # Aggiunge una colonna al dataset chiamata AP e inizializza tutti i record a 0.0.
        dataset_with_ambiti_processi[AP] = 0.0

"""
Per ogni domanda vado a vedere se lo studente ha risposto correttamente o erroneamente:
- se ha risposto correttamente, per ogni ambito o processo vado ad incrementare il valore contenuto nella cella relativa
all'ambito o al processo. L'incremento è di 1/(#domande con quell'ambito o processo).
- se ha risposto erroneamente, non incremento il valore.
Di conseguenza uno studente che ha risposto sempre correttamente a domande di un certo ambito/processo avrà il valore di quella cella a 1.
"""
if PRE_ML and CONVERT_DOMANDE_TO_AMBITI_PROCESSI:
    questions_columns = [col for col in list(cleaned_original_dataset) if re.search("^D\d", col)]

    for i, row in dataset_with_ambiti_processi.iterrows():
        for question, APs in MAPPING_DOMANDE_AMBITI_PROCESSI.items():
            if row[question] is True:
                for AP in APs:
                    dataset_with_ambiti_processi.at[i, AP] += 1 / conteggio_ambiti_processi[AP]

    dataset_ap = dataset_with_ambiti_processi.drop(questions_columns, axis=1)

    dataset_ap.to_csv(cfg.CLEANED_DATASET_WITH_AP, index=False)
else:
    dataset_ap = pd.read_csv(cfg.CLEANED_DATASET_WITH_AP)

if "Unnamed: 0" in dataset_ap.columns:
    dataset_ap.drop("Unnamed: 0", axis=1, inplace=True)

"""
Scopriamo se ci sono colonne con valori molto correlati.
"""
if PRE_ML:
    corr_matrix = dataset_ap.corr(method='pearson').round(2)
    corr_matrix.style.background_gradient(cmap='YlOrRd')

interesting_to_check_if_correlated_columns = [
                                                 # Alta correlazione fra voti della stessa materia, abbastanza correlate fra materie diverse
                                                 "voto_scritto_ita",
                                                 "voto_orale_ita",
                                                 "voto_scritto_mat",
                                                 "voto_orale_mat",
                                                 # Correlazione totale, abbastanza correlate con voti
                                                 "pu_ma_no",
                                                 # Target columns
                                                 "LIVELLI",
                                                 "DROPOUT"
                                             ] + list(ambiti_processi)

if PRE_ML:
    check_corr_dataset = dataset_ap[interesting_to_check_if_correlated_columns].corr(method='pearson').round(2)
    check_corr_dataset.style.background_gradient(cmap='YlOrRd')

"""
Rimozione colonne con alta correlazione.
"""
# Sarà fatto?

"""
Comprensione tipi colonne per trovare:
- lista feature continue (float)
- lista feature ordinali (int)
- lista feature categoriche intere (int)
- lista feature categoriche stringhe (str)
- lista feature binarie
"""
if PRE_ML:
    print("Lista colonne e tipi:")
    print(dataset_ap.info())

# Le colonne DROPOUT e LIVELLI non sono considerate in quanto colonne target (in particolare, DROPOUT è una trasformazione di LIVELLI).
continuous_features = columns_low_ratio_null_values + \
                      ["pu_ma_gr", "pu_ma_no", "Fattore_correzione_new", "Cheating", "WLE_MAT", "WLE_MAT_200",
                       "WLE_MAT_200_CORR",
                       "pu_ma_no_corr"] + \
                      list(ambiti_processi)  # Feature sui voti, feature elencate, ambiti e processi
if cfg.FILL_NAN == "remove":
    continuous_features.remove("voto_scritto_ita")
    continuous_features.remove("voto_orale_ita")
ordinal_features = ["n_stud_prev", "n_classi_prev"]
int_categorical_features = [
    "CODICE_SCUOLA", "CODICE_PLESSO", "CODICE_CLASSE", "campione", "prog",
]
str_categorical_features = [
    "sesso", "mese", "anno", "luogo", "eta", "freq_asilo_nido", "freq_scuola_materna",
    "luogo_padre", "titolo_padre", "prof_padre", "luogo_madre", "titolo_madre", "prof_madre",
    "regolarità", "cittadinanza", "cod_provincia_ISTAT", "Nome_reg",
    "Cod_reg", "Areageo_3", "Areageo_4", "Areageo_5", "Areageo_5_Istat", "sigla_provincia_istat"
]
bool_features = ["Pon"]

"""
Aggiustamento colonne con valori nulli.
"""

dataset_ap["sigla_provincia_istat"].fillna(value="ND", inplace=True)

if cfg.FILL_NAN == "remove":
    # Rimuovere colonne voti ita.
    # Rimuovere record con dati nulli in voti mat.
    dataset_ap.drop(["voto_scritto_ita", "voto_orale_ita"], axis=1, inplace=True)
    dataset_ap.dropna(subset=["voto_scritto_mat", "voto_orale_mat"], inplace=True)
else:
    for col in columns_low_ratio_null_values:
        if cfg.FILL_NAN == "median":
            replaced_value = dataset_ap[col].median()
        else: # cfg.FILL_NAN == "mean"
            replaced_value = dataset_ap[col].mean()

        dataset_ap[col].fillna(value=replaced_value, inplace=True)

"""Parte di creazione del modello"""

"""
Suddivisione dataset in training, test.
"""
df_training_set, df_test_set = train_test_split(dataset_ap, test_size=cfg.TEST_SET_PERCENT, random_state=19)

"""
Verifica sbilanciamento classi DROPOUT e NO DROPOUT nel dataset.
"""
if PRE_ML:
    nr_nodrop, nr_drop = np.bincount(dataset_ap['DROPOUT'])
    total_records = nr_drop + nr_nodrop
    print(
        f"Total number of records: {total_records} - \
    Total num. DROPOUT: {nr_drop} - \
    Total num. NO DROPOUT: {nr_nodrop} - \
    Ratio DROPOUT/TOTAL: {round(nr_drop / total_records, 2)} - \
    Ratio NO DROPOUT/TOTAL: {round(nr_nodrop / total_records, 2)} - \
    Ratio DROPOUT/NO DROPOUT: {round(nr_drop / nr_nodrop, 2)}"
    )

"""
Sampling (random undersampling o SMOTE) su training set
"""
if cfg.SAMPLING_TO_PERFORM == "random_undersampling":
    # class_nodrop contiene i record della classe sovrarappresentata, ovvero SENZA DROPOUT.
    class_nodrop = df_training_set[df_training_set['DROPOUT'] == False]
    # class_drop contiene i record della classe sottorappresentata, ovvero CON DROPOUT.
    class_drop = df_training_set[df_training_set['DROPOUT'] == True]

    # Sotto campionamento di class_drop in modo che abbia stessa cardinalità di class_nodrop.
    class_nodrop = class_nodrop.sample(len(class_drop), random_state=19)

    print(f'Class NO DROPOUT: {len(class_nodrop):,}')
    print(f'Classe DROPOUT: {len(class_drop):,}')

    df_training_set = class_drop.append(class_nodrop)
    df_training_set = df_training_set.sample(frac=1, random_state=19)
else: # cfg.SAMPLING_TO_PERFORM == "SMOTENC"
    categorical_features_indexes = [i for i in range(len(df_training_set.columns)) if
                                    df_training_set.columns[i] in str_categorical_features + int_categorical_features]

    df_training_set = df_training_set.apply(lambda col: pd.factorize(col)[0] if col.name in str_categorical_features else col)
    df_test_set = df_test_set.apply(lambda col: pd.factorize(col)[0] if col.name in str_categorical_features else col)

    sm = SMOTENC(categorical_features=categorical_features_indexes, random_state=19)
    X_train, y_train = sm.fit_resample(
        df_training_set[[col for col in df_training_set.columns if col != 'DROPOUT']],
        df_training_set['DROPOUT']
    )
    df_training_set = pd.concat([X_train, y_train], axis=1)

    X_test, y_test = sm.fit_resample(
        df_test_set[[col for col in df_test_set.columns if col != 'DROPOUT']],
        df_test_set['DROPOUT']
    )
    df_test_set = pd.concat([X_test, y_test], axis=1)

    # Se SMOTENC viene eseguito, ogni feature categorica stringa viene trasformata in feature categorica intera.
    int_categorical_features = int_categorical_features + str_categorical_features
    str_categorical_features = []

if "Unnamed: 0" in df_training_set.columns:
    df_training_set.drop("Unnamed: 0", axis=1, inplace=True)

"""
Suddivisione dataset di training in training (più piccolo di quello di partenza), validation.
"""
df_training_set, df_validation_set = train_test_split(df_training_set, test_size=cfg.VALIDATION_SET_PERCENT,
                                                      random_state=19)

"""
Conversione da Pandas DataFrame a Tensorflow Dataset.
"""


def convert_dropout_column_to_one_hot(dropout_col):
    dropout_col_one_hot = []
    for dc in dropout_col:
        if dc == 1:
            dropout_col_one_hot.append([1, 0])
        else:
            dropout_col_one_hot.append([0, 1])
    return dropout_col_one_hot


def pd_dataframe_to_tf_dataset(dataframe: pd.DataFrame):
    copied_df = dataframe.copy()
    if cfg.PROBLEM_TYPE == "classification":
        dropout_col = copied_df.pop("DROPOUT")
        dropout_col = convert_dropout_column_to_one_hot(dropout_col)
        copied_df.drop("LIVELLI", axis=1, inplace=True)
    elif cfg.PROBLEM_TYPE == "regression":
        # Si invertono i valori della colonna target LIVELLI secondo la ratio (0 -> 5, 1 -> 4, ..., 5 -> 0),
        # per poi dividerli per 5, così da mapparli nel range [0,1].
        # Tale standardizzazione vien fatta affinché le predizioni restituite dal modello possano essere associate
        # al concetto "Dropout Sì", nel caso siano > 0.6 o a "Dropout no" altrimenti.
        dropout_col = copied_df.pop("LIVELLI")
        dropout_col = dropout_col.subtract(5)
        dropout_col = dropout_col.abs()
        dropout_col = dropout_col.divide(5) # Normalizzazione dei valori della colonna da [0..5] a [0..1].
        copied_df.drop("DROPOUT", axis=1, inplace=True)
    else: # cfg.PROBLEM_TYPE == "pure_regression"
        dropout_col = copied_df.pop("LIVELLI")
        dropout_col = dropout_col.divide(5) # Normalizzazione dei valori della colonna da [0..5] a [0..1].
        copied_df.drop("DROPOUT", axis=1, inplace=True)

    """
    Dato che il dataframe ha dati eterogenei lo convertiamo a dizionario (i.e. dict(copied_df)),
    in cui le chiavi sono i nomi delle colonne e i valori sono i valori della colonna.
    Infine bisogna indicare la colonna target.
    """

    tf_dataset = tf.data.Dataset.from_tensor_slices((dict(copied_df), dropout_col))
    tf_dataset = tf_dataset.shuffle(buffer_size=len(copied_df), seed=19)
    return tf_dataset


ds_training_set = pd_dataframe_to_tf_dataset(df_training_set)
ds_validation_set = pd_dataframe_to_tf_dataset(df_validation_set)
ds_test_set = pd_dataframe_to_tf_dataset(df_test_set)

"""
Suddivisione dei Dataset in batch per sfruttare meglio le capacità hardware
(invece di elaborare un record per volta).
"""
# drop_remainder=True rimuove i record che non rientrano nei batch della dimensione fissata.
ds_training_set = ds_training_set.batch(cfg.BATCH_SIZE, drop_remainder=True)
ds_validation_set = ds_validation_set.batch(cfg.BATCH_SIZE, drop_remainder=True)
ds_test_set = ds_test_set.batch(cfg.BATCH_SIZE, drop_remainder=True)

"""
Creazione layer di input per ogni feature a partire dalle liste precedentemente definite:
- continuous_features
- ordinal_features
- int_categorical_features
- str_categorical_features
- bool_features
"""
input_layers = {}
for name, column in df_training_set.items():
    if name in ["DROPOUT", "LIVELLI"]:
        continue

    if cfg.FILL_NAN == "remove" and name in ["voto_scritto_ita", "voto_orale_ita"]:
        continue

    if name in continuous_features:
        dtype = tf.float32
    elif name in ordinal_features or name in int_categorical_features or name in bool_features:
        dtype = tf.int64
    else:  # name in str_categorical_features
        dtype = tf.string

    input_layers[name] = tf.keras.Input(shape=(), name=name, dtype=dtype)

"""
Encoding delle feature in base al loro tipo.
"""
preprocessed_features = []


def stack_dict(inputs, fun=tf.stack):
    values = []
    for key in sorted(inputs.keys()):
        values.append(tf.cast(inputs[key], tf.float32))

    return fun(values, axis=-1)


# Preprocessing colonne con dati booleani
for name in bool_features:
    inp = input_layers[name]
    inp = inp[:, tf.newaxis]
    float_value = tf.cast(inp, tf.float32)
    preprocessed_features.append(float_value)

# Preprocessing colonne con dati interi ordinali
ordinal_inputs = {}
for name in ordinal_features:
    ordinal_inputs[name] = input_layers[name]

normalizer = Normalization(axis=-1)
normalizer.adapt(stack_dict(dict(df_training_set[ordinal_features])))
ordinal_inputs = stack_dict(ordinal_inputs)
ordinal_normalized = normalizer(ordinal_inputs)
preprocessed_features.append(ordinal_normalized)

# Preprocessing colonne con dati continui
continuous_inputs = {}
for name in continuous_features:
    if cfg.FILL_NAN == "remove" and name in ["voto_scritto_ita", "voto_orale_ita"]:
        continue
    continuous_inputs[name] = input_layers[name]

normalizer = Normalization(axis=-1)
normalizer.adapt(stack_dict(dict(df_training_set[continuous_features])))
continuous_inputs = stack_dict(continuous_inputs)
continuous_normalized = normalizer(continuous_inputs)
preprocessed_features.append(continuous_normalized)

# Preprocessing colonne con dati categorici stringa
for name in str_categorical_features:
    vocab = sorted(set(df_training_set[name]))

    lookup = StringLookup(vocabulary=vocab, output_mode='one_hot')

    x = input_layers[name][:, tf.newaxis]
    x = lookup(x)

    preprocessed_features.append(x)

# Preprocessing colonne con dati categorici interi
for name in int_categorical_features:
    vocab = sorted(set(df_training_set[name]))

    lookup = IntegerLookup(vocabulary=vocab, output_mode='one_hot')

    x = input_layers[name][:, tf.newaxis]
    x = lookup(x)

    preprocessed_features.append(x)

"""
Assemblaggio dei vari layer preprocessati.
"""

preprocessed = tf.concat(preprocessed_features, axis=-1)

preprocessor = tf.keras.Model(input_layers, preprocessed)

# inizializzatore che verrà usato per i pesi dei layer con ReLU / LeakyReLU
initializer_hidden_layer = tf.keras.initializers.HeNormal(seed=19)
# inizializzatore che verrà usato per i pesi dei layer con sigmoid
initializer_output_layer = tf.keras.initializers.GlorotNormal(seed=19)

body = tf.keras.Sequential()

if cfg.DROPOUT_LAYER:
    body.add(tf.keras.layers.Dropout(rate=cfg.DROPOUT_INPUT_LAYER_RATE, seed=19))  # aggiunta dropout a layer di input

# segue l'aggiunta degli hidden layers
for _ in range(cfg.NUMBER_OF_LAYERS):
    body.add(tf.keras.layers.Dense(cfg.NEURONS, kernel_initializer=initializer_hidden_layer))

    if cfg.BATCH_NORMALIZATION == "dense_batch_activation":
        body.add(tf.keras.layers.BatchNormalization())

    if cfg.ACTIVATION_LAYER == "leaky_relu":
        body.add(tf.keras.layers.LeakyReLU())
    else:
        body.add(tf.keras.layers.ReLU())

    if cfg.DROPOUT_LAYER:
        body.add(tf.keras.layers.Dropout(rate=cfg.DROPOUT_HIDDEN_LAYER_RATE, seed=19))

    if cfg.BATCH_NORMALIZATION == "dense_activation_batch":
        body.add(tf.keras.layers.BatchNormalization())

if cfg.BATCH_NORMALIZATION == "before_output":
    body.add(tf.keras.layers.BatchNormalization())

# segue l'aggiunta dell'output layer
if cfg.PROBLEM_TYPE == "classification":
    body.add(tf.keras.layers.Dense(2, activation="softmax", kernel_initializer=initializer_output_layer))
else: # cfg.PROBLEM_TYPE == "regression" or cfg.PROBLEM_TYPE == "pure_regression"
    body.add(tf.keras.layers.Dense(1, activation="sigmoid", kernel_initializer=initializer_output_layer))

x = preprocessor(input_layers)

result = body(x)

model = tf.keras.Model(input_layers, result)

if cfg.PROBLEM_TYPE == "classification":
    main_metric = tf.keras.metrics.Accuracy(name="acc")
    loss_function = tf.keras.losses.CategoricalCrossentropy()
elif cfg.PROBLEM_TYPE == "regression":
    # 0.6 perché dopo il preprocessing, i LIVELLI in [3,4,5] è DROPOUT = True, LIVELLI in [0,1,2] è DROPOUT = False
    main_metric = tf.keras.metrics.BinaryAccuracy(name="bin_acc", threshold=0.6)  
    loss_function = tf.keras.losses.BinaryCrossentropy()
else: # cfg.PROBLEM_TYPE == "pure_regression"
    main_metric = tf.keras.metrics.MeanAbsoluteError(name="mae")
    loss_function = tf.keras.losses.MeanSquaredError()

model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=cfg.LEARNING_RATE),
              loss=loss_function,
              metrics=[
                  main_metric,
                  tf.keras.metrics.FalsePositives(name="fp"),
                  tf.keras.metrics.FalseNegatives(name="fn"),
                  tf.keras.metrics.TruePositives(name="tp"),
                  tf.keras.metrics.TrueNegatives(name="tn"),
                  tf.keras.metrics.Precision(name="prec"),
                  tf.keras.metrics.Recall(name="rec")
              ])

"""
Definizione dello stopper per evitare che la reti continui ad addestrarsi quando non ci sono miglioramenti della loss 
(val_loss = funzione di costo sul validation set) per piu' di 5 epoche
"""
early_stopper = EarlyStopping(monitor="val_loss",
                              patience=5,
                              mode="min",
                              restore_best_weights=True)

"""
Definizione della callback che permette durante il training di salvare il miglior modello calcolato.
"""
model_checkpoint = ModelCheckpoint("best_" + cfg.PROBLEM_TYPE + ".h5", monitor='val_loss', mode='min', save_best_only=True)

print("[Training]")
history = model.fit(ds_training_set,
                    epochs=cfg.EPOCH,
                    batch_size=cfg.BATCH_SIZE,
                    validation_data=ds_validation_set,
                    callbacks=([early_stopper] if cfg.EARLY_STOPPING else []) + [model_checkpoint],
                    verbose=2)

metrics = history.history
save_plots.plot_main_metric(metrics)
save_plots.plot_loss(metrics)
save_plots.plot_tp(metrics)
save_plots.plot_tn(metrics)
save_plots.plot_fp(metrics)
save_plots.plot_fn(metrics)
save_plots.plot_recall(metrics)
save_plots.plot_precision(metrics)

print("[Test]")
score = model.evaluate(ds_test_set, verbose=2)

print()
print('Results with test dataset')
print('Loss:', round(score[0], 4))
print('Accuracy:', round(score[1], 4))
print('False positives:', int(score[2]))
print('False negatives:', int(score[3]))
print('True positives:', int(score[4]))
print('True negatives:', int(score[5]))
print('Precision: ', round(score[6], 4))
print('Recall: ', round(score[7], 4))
